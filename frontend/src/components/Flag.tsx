import * as Flags from "country-flag-icons/react/3x2";

// Real per-country flags (country-flag-icons, MIT) - never emoji. England/Scotland/Wales/
// Northern Ireland get their own real flags (GB_ENG = St George's Cross), not the Union
// Flag, since our data distinguishes them as separate national teams/leagues.
const NAME_TO_ISO: Record<string, keyof typeof Flags> = {
  England: "GB_ENG",
  Scotland: "GB_SCT",
  Wales: "GB_WLS",
  "Northern Ireland": "GB_NIR",
  "United Kingdom": "GB",
  Spain: "ES",
  Italy: "IT",
  Germany: "DE",
  France: "FR",
  Portugal: "PT",
  Netherlands: "NL",
  Belgium: "BE",
  Croatia: "HR",
  Denmark: "DK",
  Sweden: "SE",
  Norway: "NO",
  Switzerland: "CH",
  Austria: "AT",
  Poland: "PL",
  Ukraine: "UA",
  Turkey: "TR",
  Türkiye: "TR",
  Greece: "GR",
  Serbia: "RS",
  "Czech Republic": "CZ",
  Czechia: "CZ",
  Slovakia: "SK",
  Slovenia: "SI",
  Hungary: "HU",
  Romania: "RO",
  Bulgaria: "BG",
  Finland: "FI",
  Iceland: "IS",
  Ireland: "IE",
  "Republic of Ireland": "IE",
  "Bosnia and Herzegovina": "BA",
  Montenegro: "ME",
  "North Macedonia": "MK",
  Albania: "AL",
  Kosovo: "XK",
  Armenia: "AM",
  Azerbaijan: "AZ",
  Georgia: "GE",
  Cyprus: "CY",
  Malta: "MT",
  Luxembourg: "LU",
  Estonia: "EE",
  Latvia: "LV",
  Lithuania: "LT",
  Belarus: "BY",
  Moldova: "MD",
  Kazakhstan: "KZ",
  "Faroe Islands": "FO",
  Andorra: "AD",
  Gibraltar: "GI",
  Liechtenstein: "LI",
  "San Marino": "SM",
  Europe: "EU",
};

export function Flag({ country, className }: { country: string | null; className?: string }) {
  const iso = country ? NAME_TO_ISO[country] : undefined;
  const FlagSvg = iso ? Flags[iso] : undefined;
  if (!FlagSvg) {
    // No emoji fallback (never emoji) - a neutral drawn globe/dot for international
    // competitions or a country we don't have a mapping for yet.
    return (
      <svg viewBox="0 0 3 2" className={className} aria-hidden="true">
        <rect width="3" height="2" rx="0.2" fill="var(--muted-2)" opacity="0.4" />
        <circle cx="1.5" cy="1" r="0.55" fill="none" stroke="var(--muted)" strokeWidth="0.08" />
      </svg>
    );
  }
  return <FlagSvg className={className} title={country ?? undefined} />;
}
