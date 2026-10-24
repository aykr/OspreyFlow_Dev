"""The Lua scripts that keep the working set's access index with its bodies (ADR-124 Amendment 4).

Each write to the working set is one script (`EVAL`): it writes the bodies, moves the counts, keeps
the per-element entries and the adjacency, and counts up the version, atomically, so no reader sees
a body without its entry or a count that does not match the entries. `IndexState` in
`access_index.py` is the same logic in Python, which the in-memory fake keeps and the tests hold
the scripts to. The store runs a write in chunks of at most `_SCRIPT_CHUNK` elements, each a script
that leaves the bodies and the index consistent on its own, so no script holds Valkey for the length
of a branch or a restore.

The keys, in this order, for every script:

    1 nodes (bodies)          2 edges (bodies)        3 access_nodes (node -> signature key)
    4 access_edges (link -> entry)                    5 sig_defs (signature key -> definition)
    6 sig_numbers (signature id -> key)               7 meta (one hash of the scalars)
    8 node_counts             9 edge_counts          10 adjacency (a sorted set)
   11 seq                    12 deltas               13 threshold

`meta` holds `sig_counter`, `sigs_version`, `version`, `epoch` and `self_links`, as fields of one
hash so that they are lost together and a reader's check sees it. The last three keys are only
refreshed here (the TTL), so that a write needs no second round trip. The arguments start with the
idle TTL in seconds and a fresh epoch token (used only if the case has none), followed by what the
script writes.

**A script that finds the index damaged stops and says so** (`access index damaged`): a signature
number with no definition, a link in the adjacency with no entry. The store answers by rebuilding
the index from the bodies and running the write again. A script reads and checks everything it is
about to change before it changes it where it can (`move_node`), so that it stops before a partial
write.

How a link's triple moves: a link is counted under (its signature, its source end's signature, its
target end's signature), an end that is not stored being `absent`. When a node is added, removed or
given another signature, every link at it (the adjacency finds them, whether or not the node is
stored) has its triple counted out under the node's old signature and in under its new one. When a
link is replaced its old triple is counted out first.

**What bounds a script.** A chunk is at most `_SCRIPT_CHUNK` elements, and the work per element is
a few commands, except a node's addition, removal or change of signature, whose work is the number
of links at the node (the adjacency range and one entry read and two counts for each). A hub's
degree is the bound on one node's removal: a node with every link of a case at 250,000 links costs
that many
steps in the one script that removes it.
"""

from __future__ import annotations

PRELUDE = r"""
local ABSENT = 'absent'
local META = KEYS[7]

local function damaged(what)
  error('access index damaged: ' .. what)
end

local function ensure_sig(id, def)
  local key = redis.call('HGET', KEYS[6], id)
  if key then
    if redis.call('HEXISTS', KEYS[5], key) == 0 then
      damaged('signature ' .. key .. ' has no definition')
    end
    return key
  end
  key = tostring(redis.call('HINCRBY', META, 'sig_counter', 1))
  -- A number that is already defined is not ours to give: the counter was lost or went back, and
  -- writing here would change what a signature that readers hold by number means.
  if redis.call('HEXISTS', KEYS[5], key) == 1 then
    damaged('signature ' .. key .. ' already defined')
  end
  redis.call('HSET', KEYS[6], id, key)
  redis.call('HSET', KEYS[5], key, def)
  redis.call('HINCRBY', META, 'sigs_version', 1)
  return key
end

local function count(key, field, delta)
  local value = redis.call('HINCRBY', key, field, delta)
  if value == 0 then redis.call('HDEL', key, field) end
end

local function parse_edge(blob)
  local c1 = string.find(blob, ':', 1, true)
  local l1 = tonumber(string.sub(blob, 1, c1 - 1))
  local sig = string.sub(blob, c1 + 1, c1 + l1)
  local p = c1 + l1 + 1
  local c2 = string.find(blob, ':', p, true)
  local l2 = tonumber(string.sub(blob, p, c2 - 1))
  local source = string.sub(blob, c2 + 1, c2 + l2)
  local target = string.sub(blob, c2 + l2 + 1)
  return sig, source, target
end

local function edge_blob(sig, source, target)
  return #sig .. ':' .. sig .. #source .. ':' .. source .. target
end

-- A link's entry, or the script stops: an entry that is not there is not something to count from.
local function edge_entry(edge_id)
  local blob = redis.call('HGET', KEYS[4], edge_id)
  if not blob then damaged('link ' .. edge_id .. ' has no entry') end
  return parse_edge(blob)
end

local function end_sig(node)
  local sig = redis.call('HGET', KEYS[3], node)
  if sig then return sig end
  return ABSENT
end

local function triple(edge_sig, source_sig, target_sig)
  return edge_sig .. ',' .. source_sig .. ',' .. target_sig
end

local function prefix(node)
  return #node .. ':' .. node
end

local function incident(node)
  local p = prefix(node)
  local members = redis.call('ZRANGEBYLEX', KEYS[10], '[' .. p, '[' .. p .. '\255')
  local edges = {}
  for i, member in ipairs(members) do edges[i] = string.sub(member, #p + 1) end
  return edges
end

-- Count every link at `node` out under its signature `old` and in under `new`. Everything is read
-- and checked first, and counted after, so that a damaged entry stops the script before a count
-- has moved.
local function move_node(node, old, new)
  local changes = {}
  for _, edge_id in ipairs(incident(node)) do
    local sig, source, target = edge_entry(edge_id)
    local function at(end_node, node_sig)
      if end_node == node then return node_sig end
      return end_sig(end_node)
    end
    changes[#changes + 1] = {
      triple(sig, at(source, old), at(target, old)),
      triple(sig, at(source, new), at(target, new)),
    }
  end
  for _, change in ipairs(changes) do
    count(KEYS[9], change[1], -1)
    count(KEYS[9], change[2], 1)
  end
end

local function finish()
  redis.call('HINCRBY', META, 'version', 1)
  redis.call('HSETNX', META, 'epoch', ARGV[2])
  for i = 1, 13 do redis.call('EXPIRE', KEYS[i], tonumber(ARGV[1])) end
  return 1
end
"""

#: ARGV from 3: for each node, its id, its body, its signature id and its signature definition.
ADD_NODES = (
    PRELUDE
    + r"""
local i = 3
while i <= #ARGV do
  local id, body, sig_id, def = ARGV[i], ARGV[i + 1], ARGV[i + 2], ARGV[i + 3]
  i = i + 4
  local key = ensure_sig(sig_id, def)
  local old = redis.call('HGET', KEYS[3], id)
  if old ~= key then
    local old_sig = ABSENT
    if old then old_sig = old end
    move_node(id, old_sig, key)
    if old then count(KEYS[8], old, -1) end
    count(KEYS[8], key, 1)
    redis.call('HSET', KEYS[3], id, key)
  end
  -- The body last, as in ADD_EDGES: a move that stops the script has written nothing of the node.
  redis.call('HSET', KEYS[1], id, body)
end
return finish()
"""
)

#: ARGV from 3: each node id.
REMOVE_NODES = (
    PRELUDE
    + r"""
for i = 3, #ARGV do
  local id = ARGV[i]
  local old = redis.call('HGET', KEYS[3], id)
  if old then
    move_node(id, old, ABSENT)
    count(KEYS[8], old, -1)
    redis.call('HDEL', KEYS[3], id)
  end
  redis.call('HDEL', KEYS[1], id)
end
return finish()
"""
)

#: ARGV from 3: for each link, its id, its body, its signature id and definition, its source and
#: its target.
ADD_EDGES = (
    PRELUDE
    + r"""
local i = 3
while i <= #ARGV do
  local id, body, sig_id, def = ARGV[i], ARGV[i + 1], ARGV[i + 2], ARGV[i + 3]
  local source, target = ARGV[i + 4], ARGV[i + 5]
  i = i + 6
  local key = ensure_sig(sig_id, def)
  if redis.call('HEXISTS', KEYS[4], id) == 1 then
    local old_sig, old_source, old_target = edge_entry(id)
    count(KEYS[9], triple(old_sig, end_sig(old_source), end_sig(old_target)), -1)
    redis.call('ZREM', KEYS[10], prefix(old_source) .. id)
    redis.call('ZREM', KEYS[10], prefix(old_target) .. id)
    if old_source == old_target then redis.call('HINCRBY', META, 'self_links', -1) end
  end
  if source == target then redis.call('HINCRBY', META, 'self_links', 1) end
  redis.call('HSET', KEYS[4], id, edge_blob(key, source, target))
  redis.call('ZADD', KEYS[10], 0, prefix(source) .. id)
  redis.call('ZADD', KEYS[10], 0, prefix(target) .. id)
  count(KEYS[9], triple(key, end_sig(source), end_sig(target)), 1)
  redis.call('HSET', KEYS[2], id, body)
end
return finish()
"""
)

#: ARGV from 3: each link id.
REMOVE_EDGES = (
    PRELUDE
    + r"""
for i = 3, #ARGV do
  local id = ARGV[i]
  if redis.call('HEXISTS', KEYS[4], id) == 1 then
    local sig, source, target = edge_entry(id)
    count(KEYS[9], triple(sig, end_sig(source), end_sig(target)), -1)
    redis.call('ZREM', KEYS[10], prefix(source) .. id)
    redis.call('ZREM', KEYS[10], prefix(target) .. id)
    if source == target then redis.call('HINCRBY', META, 'self_links', -1) end
    redis.call('HDEL', KEYS[4], id)
  end
  redis.call('HDEL', KEYS[2], id)
end
return finish()
"""
)
