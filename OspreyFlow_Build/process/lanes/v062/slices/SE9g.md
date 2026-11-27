# SE9g: A board's picture is only ever an image: `choose_picture` refuses, and `picture_file` answers as none, any Document whose reference is not one of the four image types

**Security part, Conduit. GG4f2 waits for it** (the owner's answers to the overnight drafts, 27 November 2026, after 09:40 UTC; RULINGS.md), from GG4f2's question 3b.

## The finding (GG4f2's draft)

`services/api/boards.py` `choose_picture` (about line 1144) checks only the Document's `media_kind`. `picture_file` (about line 1204) serves the file by its stored reference's extension. So a "picture" Document with a `.pdf` file behind it would be served inline as a board's picture. Re-read the code; lines move.

## The rule

- `choose_picture` **refuses** (its existing refusal shape; name it) any Document whose stored reference is not one of the four image types that `picture_file` already serves. Read that list from the code, never a new copy.
- `picture_file` **answers as none**, exactly as for an item with no picture, for any such Document already chosen before this part.
- Both cases are decided on the stored reference, never on the file name the client sent.

## Acceptance test

`OspreyFlow_Build/tests/services/api/test_board_picture_image_types.py` (new, pure, using `board_fakes.py`). For each of the four image types: accepted and served. For a `.pdf`, a `.html`, an `.svg` if it is not one of the four, and no extension: `choose_picture` refuses, and `picture_file` answers as none. **Red first at the real call site**, with the check removed from `choose_picture`, and separately from `picture_file` (rule 15).

## Out of scope

GG4f2's page; the media store's addressing; any new image type.
