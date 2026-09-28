import { permanentRedirect } from "next/navigation";

// The old per-match replay pages only served a fixed set of historical matches that Replay
// no longer shows at all (Replay is yesterday, nothing else) - send any old link to /replay.
export default function OldReplayMatchPage() {
  permanentRedirect("/replay");
}
