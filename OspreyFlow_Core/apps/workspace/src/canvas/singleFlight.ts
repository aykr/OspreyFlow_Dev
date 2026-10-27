// One run at a time. Select what is lit reads the server and then replaces the selection; a second
// press while the first is being read must not start a second read, whose answer would race the first
// and record the first's selection as the one to go back to.

/** Returns a runner: it runs `task` unless an earlier task is still running, and resolves to whether
 * it ran. A task that fails frees the runner and its error reaches the caller. */
export function singleFlight(): (task: () => Promise<void>) => Promise<boolean> {
  let running = false;
  return async (task) => {
    if (running) return false;
    running = true;
    try {
      await task();
      return true;
    } finally {
      running = false;
    }
  };
}
