// Replay = the viewer's local "yesterday" (item 6). The browser is the only place that knows
// the viewer's timezone, so it reports its UTC offset (minutes EAST of UTC - the negation of
// Date.getTimezoneOffset()) and the server derives "yesterday" from the real clock plus that
// offset at request time (see kickcast_api/routes/replay.py).
export function tzOffsetMinutesEast(now: Date = new Date()): number {
  const offset = -now.getTimezoneOffset();
  return offset === 0 ? 0 : offset; // avoid -0
}
