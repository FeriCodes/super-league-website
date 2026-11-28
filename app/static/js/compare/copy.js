(function () {
  window.CompareApp = window.CompareApp || {};

  const TEAM_ABBR = {
    "Arsenal": "ARS",
    "Aston Villa": "AVL",
    "Bournemouth": "BOU",
    "Brentford": "BRE",
    "Brighton": "BHA",
    "Burnley": "BUR",
    "Chelsea": "CHE",
    "Crystal Palace": "CRY",
    "Everton": "EVE",
    "Fulham": "FUL",
    "Leeds": "LEE",
    "Liverpool": "LIV",
    "Manchester City": "MCI",
    "Manchester United": "MUN",
    "Newcastle": "NEW",
    "Nottingham Forest": "NFO",
    "Sunderland": "SUN",
    "Tottenham": "TOT",
    "West Ham": "WHU",
    "Wolves": "WOL"
  };

  function getAbbr(name) {
    if (TEAM_ABBR[name]) return TEAM_ABBR[name];
    return String(name || "TM")
      .replace(/[^A-Za-z]/g, "")
      .slice(0, 3)
      .toUpperCase()
      .padEnd(3, " ");
  }

  function trunc(str, maxLen) {
    const s = String(str || "");
    return s.length > maxLen ? s.slice(0, maxLen - 1) + "." : s;
  }

  function padR(str, len) {
    return String(str).padEnd(len, " ");
  }

  function padL(str, len) {
    return String(str).padStart(len, " ");
  }

  function formatChips(chips) {
    if (!chips || !chips.length) return "None";
    return chips.map((c) => `${c.count}x ${c.name}`).join(", ");
  }

  function formatCaps(caps) {
    if (!caps || !caps.length) return "None";
    return caps.map((c) => `${c.name} ${c.count}x`).join(", ");
  }

  function buildTableText(data) {
    const abbrA = getAbbr(data.team_a);
    const abbrB = getAbbr(data.team_b);
    const sa = data.summary_a;
    const sb = data.summary_b;

    const hitsA = sa.hits > 0 ? `-${sa.hits}` : "0";
    const hitsB = sb.hits > 0 ? `-${sb.hits}` : "0";

    const headerLines = [
      `⚔️ ${data.team_a} vs ${data.team_b} (GW ${data.gameweek})`,
      `📊 Score: ${sa.points} - ${sb.points}`,
      `🎯 Hits: ${hitsA} | ${hitsB}`,
      `⏳ Left: ${sa.left}/${sa.total_slots} | ${sb.left}/${sb.total_slots}`,
      `⚡ Chips: ${abbrA} (${formatChips(sa.chips)}) | ${abbrB} (${formatChips(sb.chips)})`,
      `©️ Caps: ${abbrA} (${formatCaps(sa.captains)}) | ${abbrB} (${formatCaps(sb.captains)})`
    ];

    const tableHeader = `${padR("Player", 13)} ${padL(abbrA, 3)} ${padL(abbrB, 3)} ${padL("Diff", 4)} ${padL("Pt", 3)}`;
    const divider = "-".repeat(tableHeader.length);
    const tableBlocks = [];

    (data.sections || []).forEach((section) => {
      if (!section.players || !section.players.length) return;
      const rows = [section.pos, tableHeader, divider];

      section.players.forEach((p) => {
        const nameCol = padR(trunc(p.name, 13), 13);
        const colA = padL(p.count_a > 0 ? `${p.count_a}x` : "-", 3);
        const colB = padL(p.count_b > 0 ? `${p.count_b}x` : "-", 3);

        let diffStr = " = ";
        if (p.diff > 0) {
          diffStr = `<+${p.diff}`;
        } else if (p.diff < 0) {
          diffStr = `+${p.abs_diff}>`;
        }
        const colDiff = padL(diffStr, 4);
        const cleanPts = String(p.pts ?? "-").replace(/\s*pts?$/i, "").trim();
        const colPts = padL(cleanPts, 3);

        rows.push(`${nameCol} ${colA} ${colB} ${colDiff} ${colPts}`);
      });

      tableBlocks.push(rows.join("\n"));
    });

    return `${headerLines.join("\n")}\n\n\`\`\`\n${tableBlocks.join("\n\n")}\n\`\`\``;
  }

  function fallbackCopy(text) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }

  function initCopyFeature() {
    const copyBtn = document.getElementById("btn-copy-telegram");
    const exportDataEl = document.getElementById("compare-export-data");
    if (!copyBtn || !exportDataEl) return;

    let copyTimer = null;
    copyBtn.addEventListener("click", async function () {
      const data = JSON.parse(exportDataEl.textContent);
      const textToCopy = buildTableText(data);

      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(textToCopy);
        } else {
          fallbackCopy(textToCopy);
        }
      } catch (err) {
        fallbackCopy(textToCopy);
      }

      const iconEl = document.getElementById("copy-btn-icon");
      const labelEl = document.getElementById("copy-btn-label");
      copyBtn.classList.add("is-copied");
      if (iconEl) iconEl.textContent = "✅";
      if (labelEl) labelEl.textContent = "Copied!";

      clearTimeout(copyTimer);
      copyTimer = setTimeout(() => {
        copyBtn.classList.remove("is-copied");
        if (iconEl) iconEl.textContent = "📋";
        if (labelEl) labelEl.textContent = "Copy";
      }, 2000);
    });
  }

  window.CompareApp.initCopyFeature = initCopyFeature;
})();