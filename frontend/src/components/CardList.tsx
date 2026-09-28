import type { CardEvent } from "@/lib/api";

// Yellow/red cards, same shape as the goal timeline. Renders NOTHING with no card data (most
// matches - only API-Football supplies cards), never a "not available" message.
export function CardList({
  cards,
  home,
  away,
  bare = false,
}: {
  cards: CardEvent[] | undefined;
  home: { id: string; name: string };
  away: { id: string; name: string };
  bare?: boolean; // no card chrome/heading - for embedding inside another card
}) {
  if (!cards || cards.length === 0) return null;
  const teamName = (id: string | null) => (id === home.id ? home.name : id === away.id ? away.name : null);
  const Wrapper = bare ? "div" : "section";
  return (
    <Wrapper className={bare ? "mt-2" : "glass p-5"} aria-label="Cards">
      {!bare && <h2 className="mb-2 text-lg font-semibold text-foreground">Cards</h2>}
      <ul className="space-y-1.5">
        {cards.map((c, i) => (
          <li key={`${c.minute}-${c.player}-${i}`} className="flex items-center gap-3 text-sm">
            <span className="w-9 shrink-0 tabular-nums text-muted-2">{c.minute != null ? `${c.minute}'` : ""}</span>
            <span
              role="img"
              aria-label={c.card === "red" ? "Red card" : "Yellow card"}
              className={`h-3.5 w-2.5 shrink-0 rounded-[2px] ${c.card === "red" ? "bg-red-500" : "bg-yellow-400"}`}
            />
            <span className="text-foreground">
              {c.player}
              {teamName(c.team_id) && <span className="text-muted-2"> &mdash; {teamName(c.team_id)}</span>}
            </span>
          </li>
        ))}
      </ul>
    </Wrapper>
  );
}
