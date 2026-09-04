var __defProp = Object.defineProperty;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __glob = (map) => (path) => {
  var fn = map[path];
  if (fn) return fn();
  throw new Error("Module not found in bundle: " + path);
};
var __esm = (fn, res, err) => function __init() {
  if (err) throw err[0];
  try {
    return fn && (res = (0, fn[__getOwnPropNames(fn)[0]])(fn = 0)), res;
  } catch (e) {
    throw err = [e], e;
  }
};
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};

// src/services/factorService.js
async function get(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${path} responded ${response.status}`);
  return response.json();
}
async function loadModels() {
  const body = await get("/api/factors");
  return { models: body.models || [], withdrawn: body.withdrawn || [] };
}
async function loadFilmAxes(reading, filmId) {
  const query = new URLSearchParams({
    variant: reading?.variant || "subs",
    ...reading?.bank_version ? { bank: reading.bank_version } : {}
  });
  return get(`/api/factors/${encodeURIComponent(reading.scorer)}/films/${encodeURIComponent(filmId)}?${query}`);
}
async function loadFilmSets() {
  return get("/api/factors/sets");
}
async function loadProductFilmAxes(filmId) {
  return get(`/api/factors/product/films/${encodeURIComponent(filmId)}`);
}
async function loadFactors(scorer, variant = "subs", bank = "") {
  const query = new URLSearchParams({ variant });
  if (bank) query.set("bank", bank);
  return get(`/api/factors/${encodeURIComponent(scorer)}?${query}`);
}
function isClear(factor) {
  return (factor.margin ?? 0) >= CLEAR_MARGIN;
}
async function loadTaste() {
  try {
    const body = await get("/api/factors/taste");
    return {
      dimensions: body.dimensions || [],
      films: body.films || [],
      findings: body.findings || {}
    };
  } catch {
    return { dimensions: [], films: [], findings: {} };
  }
}
var CLEAR_MARGIN;
var init_factorService = __esm({
  "src/services/factorService.js"() {
    CLEAR_MARGIN = 0.05;
  }
});

// src/components/atlas/Verdicts.jsx
import React from "react";
import { Fragment, jsx, jsxs } from "react/jsx-runtime";
function Verdicts({ verdicts, poleHigh, poleLow }) {
  const [all, setAll] = React.useState(false);
  if (!verdicts?.length) return null;
  const heaviest = Math.max(...verdicts.map((v) => v.weight || 0), 1e-4);
  const shown2 = all ? verdicts : verdicts.slice(0, HEAVIEST);
  const hidden = verdicts.length - shown2.length;
  return /* @__PURE__ */ jsxs(Fragment, { children: [
    /* @__PURE__ */ jsx("ul", { className: "verdicts", children: shown2.map((verdict) => {
      const adds = verdict.points_to === "high";
      const pole = adds ? poleHigh : poleLow;
      return /* @__PURE__ */ jsxs("li", { className: adds ? "adds" : "subtracts", children: [
        /* @__PURE__ */ jsx("span", { className: "verdict-sign", "aria-hidden": "true", children: adds ? "+" : "\u2212" }),
        /* @__PURE__ */ jsxs("span", { className: "verdict-body", children: [
          /* @__PURE__ */ jsx("span", { className: "verdict-text", children: verdict.text }),
          /* @__PURE__ */ jsxs("span", { className: "verdict-effect", children: [
            /* @__PURE__ */ jsx("b", { children: verdict.emphatic ? verdict.verdict === "affirms" ? "Strongly affirmed" : "Strongly denied" : verdict.verdict === "affirms" ? "Affirmed" : "Denied" }),
            /* @__PURE__ */ jsx("i", { "aria-hidden": "true", children: "\u2192" }),
            /* @__PURE__ */ jsx("em", { children: pole }),
            verdict.reverse_keyed && /* @__PURE__ */ jsx("u", { title: "Affirming this proposition means taking the opposite side of the axis from how the sentence reads", children: "reads backwards" })
          ] }),
          verdict.weight != null && /* @__PURE__ */ jsxs("span", { className: "verdict-measure", children: [
            /* @__PURE__ */ jsx(
              "span",
              {
                className: "verdict-weight",
                title: `How much this proposition defines this axis: loading ${verdict.weight}, drawn against the strongest one here`,
                children: /* @__PURE__ */ jsx("i", { style: { inlineSize: `${Math.round(verdict.weight / heaviest * 100)}%` } })
              }
            ),
            verdict.contribution != null && /* @__PURE__ */ jsxs("b", { title: "What this proposition added to the film's position on this axis. Every proposition listed here sums to that position.", children: [
              verdict.contribution >= 0 ? "+" : "\u2212",
              Math.abs(verdict.contribution).toFixed(3)
            ] })
          ] }),
          verdict.evidence && /* @__PURE__ */ jsx("span", { className: "verdict-evidence", children: verdict.evidence })
        ] })
      ] }, verdict.item_id);
    }) }),
    hidden > 0 && /* @__PURE__ */ jsxs("button", { type: "button", className: "verdicts-more", onClick: () => setAll(true), children: [
      "Show the other ",
      hidden,
      " propositions that count toward this axis"
    ] }),
    all && verdicts.length > HEAVIEST && /* @__PURE__ */ jsxs("button", { type: "button", className: "verdicts-more", onClick: () => setAll(false), children: [
      "Show only the heaviest ",
      HEAVIEST
    ] })
  ] });
}
var HEAVIEST;
var init_Verdicts = __esm({
  "src/components/atlas/Verdicts.jsx"() {
    HEAVIEST = 12;
  }
});

// src/components/atlas/FactorDistribution.jsx
import React2 from "react";
import { Fragment as Fragment2, jsx as jsx2, jsxs as jsxs2 } from "react/jsx-runtime";
function FactorDistribution({ films, poleLow, poleHigh, reading, factorId }) {
  const [open, setOpen] = React2.useState(null);
  if (!films?.length) return null;
  const rows = films.map((film, index) => typeof film === "number" ? { film_id: `n${index}`, title: null, score: film } : film);
  const bins = Array.from({ length: BINS }, () => []);
  for (const film of rows) bins[binOf(film.score)].push(film);
  const tallest = Math.max(...bins.map((bin) => bin.length));
  const mean = rows.reduce((total, film) => total + film.score, 0) / rows.length;
  const positive = rows.filter((film) => film.score > 0.2).length;
  const negative = rows.filter((film) => film.score < -0.2).length;
  const middle = rows.length - positive - negative;
  const chosen = open == null ? null : bins[open];
  return /* @__PURE__ */ jsxs2("div", { className: "distribution", children: [
    /* @__PURE__ */ jsxs2(
      "div",
      {
        className: "distribution-bars",
        "aria-label": `Score distribution across ${rows.length} films`,
        children: [
          bins.map((bin, index) => {
            const at = index / (BINS - 1) * 2 - 1;
            return /* @__PURE__ */ jsx2(
              "button",
              {
                type: "button",
                className: `distribution-bin ${sideOf(index)} ${open === index ? "open" : ""}`,
                "aria-pressed": open === index,
                disabled: !bin.length,
                onClick: () => setOpen(open === index ? null : index),
                title: `${bin.length} film${bin.length === 1 ? "" : "s"} near ${signed(at)}`,
                children: /* @__PURE__ */ jsx2("i", { style: { blockSize: `${tallest ? bin.length / tallest * 100 : 0}%` } })
              },
              index
            );
          }),
          /* @__PURE__ */ jsx2("u", { className: "distribution-mid" })
        ]
      }
    ),
    /* @__PURE__ */ jsxs2("div", { className: "distribution-scale", children: [
      /* @__PURE__ */ jsxs2("span", { className: "scale-low", children: [
        "\u2190 ",
        poleLow || "\u22121"
      ] }),
      /* @__PURE__ */ jsxs2("span", { className: "distribution-mean", children: [
        rows.length,
        " films \xB7 mean ",
        signed(mean)
      ] }),
      /* @__PURE__ */ jsxs2("span", { className: "scale-high", children: [
        poleHigh || "+1",
        " \u2192"
      ] })
    ] }),
    /* @__PURE__ */ jsxs2("p", { className: "distribution-split", children: [
      /* @__PURE__ */ jsx2("b", { className: "low", children: negative }),
      " toward ",
      poleLow || "denying",
      " \xB7 ",
      middle,
      " near the middle \xB7 ",
      /* @__PURE__ */ jsx2("b", { className: "high", children: positive }),
      " toward ",
      poleHigh || "affirming",
      positive / rows.length > 0.85 && /* @__PURE__ */ jsx2("em", { children: " \u2014 almost every film agrees here, so this axis says more about the corpus than it distinguishes between films." })
    ] }),
    chosen?.length ? /* @__PURE__ */ jsxs2("div", { className: `distribution-open ${sideOf(open)}`, children: [
      /* @__PURE__ */ jsxs2("span", { className: "distribution-open-label", children: [
        chosen.length,
        " film",
        chosen.length === 1 ? "" : "s",
        " around",
        " ",
        signed(open / (BINS - 1) * 2 - 1),
        sideOf(open) === "mid" ? " \u2014 weighed it both ways" : sideOf(open) === "low" ? ` \u2014 ${poleLow || "toward \u22121"}` : ` \u2014 ${poleHigh || "toward +1"}`
      ] }),
      /* @__PURE__ */ jsx2(
        AnchorList,
        {
          films: [...chosen].sort((a, b) => b.score - a.score),
          reading,
          factorId
        }
      )
    ] }) : /* @__PURE__ */ jsx2("p", { className: "distribution-hint", children: "Click a bar to see which films are in it." })
  ] });
}
function FilmOnAxis({ reading, factorId, film }) {
  const [state, setState] = React2.useState({ status: "loading" });
  React2.useEffect(() => {
    let live = true;
    setState({ status: "loading" });
    loadFilmAxes(reading, film.film_id).then((data) => {
      if (!live) return;
      const match = (data.factors || []).find((f) => f.factor_id === factorId);
      setState({ status: "ready", factor: match });
    }).catch(() => live && setState({ status: "failed" }));
    return () => {
      live = false;
    };
  }, [reading?.scorer, reading?.variant, reading?.bank_version, factorId, film.film_id]);
  if (state.status === "loading") return /* @__PURE__ */ jsx2("p", { className: "film-why-note", children: "Reading its answers\u2026" });
  if (state.status === "failed" || !state.factor?.verdicts?.length) {
    return /* @__PURE__ */ jsx2("p", { className: "film-why-note", children: "No recorded answers for this film on this axis." });
  }
  const verdicts = state.factor.verdicts;
  const high = verdicts.filter((v) => v.points_to === "high").length;
  const flipped = verdicts.filter((v) => v.reverse_keyed).length;
  const heaviest = Math.max(...verdicts.map((v) => v.weight || 0), 1e-4);
  return /* @__PURE__ */ jsxs2("div", { className: "film-why", children: [
    /* @__PURE__ */ jsxs2("p", { className: "film-why-note", children: [
      high,
      " of ",
      verdicts.length,
      " answers point to ",
      /* @__PURE__ */ jsx2("b", { children: state.factor.pole_high_label }),
      " ",
      "\u2014 which is what puts it at ",
      /* @__PURE__ */ jsx2("b", { children: signed(film.score) }),
      ".",
      !!flipped && ` ${flipped} of them by denying the opposite.`
    ] }),
    /* @__PURE__ */ jsx2(
      Verdicts,
      {
        verdicts,
        poleHigh: state.factor.pole_high_label,
        poleLow: state.factor.pole_low_label
      }
    )
  ] });
}
function AnchorList({ films, reading, factorId }) {
  const [openId, setOpenId] = React2.useState(null);
  return /* @__PURE__ */ jsx2("ul", { children: films.map((film) => /* @__PURE__ */ jsxs2("li", { className: openId === film.film_id ? "open" : "", children: [
    /* @__PURE__ */ jsxs2(
      "button",
      {
        type: "button",
        "aria-expanded": openId === film.film_id,
        onClick: () => setOpenId(openId === film.film_id ? null : film.film_id),
        children: [
          /* @__PURE__ */ jsx2("b", { children: film.title }),
          /* @__PURE__ */ jsx2("em", { children: signed(film.score) }),
          /* @__PURE__ */ jsxs2("span", { children: [
            film.items,
            " item",
            film.items === 1 ? "" : "s"
          ] })
        ]
      }
    ),
    openId === film.film_id && /* @__PURE__ */ jsx2(FilmOnAxis, { reading, factorId, film })
  ] }, film.film_id)) });
}
function FilmAnchors({
  high,
  low,
  poleHigh,
  poleLow,
  highLabel,
  lowLabel,
  reading,
  factorId
}) {
  if (!high?.length && !low?.length) return null;
  return /* @__PURE__ */ jsxs2("div", { className: "anchors", children: [
    /* @__PURE__ */ jsxs2("div", { className: "anchors-side high", children: [
      /* @__PURE__ */ jsxs2("span", { className: "anchors-label", children: [
        "Most ",
        highLabel || "affirming"
      ] }),
      poleHigh && /* @__PURE__ */ jsx2("p", { className: "anchors-pole", children: poleHigh }),
      /* @__PURE__ */ jsx2(AnchorList, { films: high, reading, factorId })
    ] }),
    /* @__PURE__ */ jsxs2("div", { className: "anchors-side low", children: [
      /* @__PURE__ */ jsxs2("span", { className: "anchors-label", children: [
        "Most ",
        lowLabel || "denying"
      ] }),
      poleLow && /* @__PURE__ */ jsx2("p", { className: "anchors-pole", children: poleLow }),
      /* @__PURE__ */ jsx2(AnchorList, { films: low, reading, factorId })
    ] })
  ] });
}
function FactorPropositions({ propositions, poleHigh, poleLow }) {
  if (!propositions?.length) return null;
  const strongest = Math.max(...propositions.map((r) => Math.abs(r.loading || 0)), 1e-4);
  return /* @__PURE__ */ jsxs2("table", { className: "atlas-table proposition-table", children: [
    /* @__PURE__ */ jsx2("thead", { children: /* @__PURE__ */ jsxs2("tr", { children: [
      /* @__PURE__ */ jsx2("th", { children: "proposition" }),
      /* @__PURE__ */ jsx2("th", { title: "How much this proposition defines the axis, and which end affirming it puts a film on", children: "strength" }),
      /* @__PURE__ */ jsx2("th", { children: "affirmed" }),
      /* @__PURE__ */ jsx2("th", { children: "denied" })
    ] }) }),
    /* @__PURE__ */ jsx2("tbody", { children: propositions.map((row) => {
      const loading = row.loading;
      const high = (loading ?? 0) >= 0;
      const pole = high ? poleHigh : poleLow;
      return /* @__PURE__ */ jsxs2("tr", { children: [
        /* @__PURE__ */ jsx2("td", { children: row.text }),
        /* @__PURE__ */ jsx2(
          "td",
          {
            className: `prop-strength ${high ? "adds" : "subtracts"}`,
            title: pole ? `Affirming this puts a film toward ${pole}` : void 0,
            children: loading == null ? "\u2014" : /* @__PURE__ */ jsxs2(Fragment2, { children: [
              /* @__PURE__ */ jsx2("span", { className: "prop-bar", children: /* @__PURE__ */ jsx2("i", { style: { inlineSize: `${Math.round(Math.abs(loading) / strongest * 100)}%` } }) }),
              /* @__PURE__ */ jsxs2("span", { className: "prop-num", children: [
                high ? "+" : "\u2212",
                Math.abs(loading).toFixed(2)
              ] })
            ] })
          }
        ),
        /* @__PURE__ */ jsx2("td", { children: /* @__PURE__ */ jsx2("b", { children: row.affirms }) }),
        /* @__PURE__ */ jsx2("td", { children: row.denies || /* @__PURE__ */ jsx2("span", { className: "never-denied", title: "No film denied this, so it cannot separate films", children: "0" }) })
      ] }, row.item_id);
    }) })
  ] });
}
var BINS, binOf, sideOf, signed;
var init_FactorDistribution = __esm({
  "src/components/atlas/FactorDistribution.jsx"() {
    init_factorService();
    init_Verdicts();
    BINS = 17;
    binOf = (score) => Math.min(BINS - 1, Math.max(0, Math.round((score + 1) / 2 * (BINS - 1))));
    sideOf = (index) => index === (BINS - 1) / 2 ? "mid" : index < (BINS - 1) / 2 ? "low" : "high";
    signed = (value) => `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
  }
});

// src/components/atlas/Factors.jsx
import React3 from "react";
import { Fragment as Fragment3, jsx as jsx3, jsxs as jsxs3 } from "react/jsx-runtime";
function Scree({ eigenvalues, thresholds }) {
  const rows = eigenvalues.map((observed, index) => ({
    index: index + 1,
    observed,
    threshold: thresholds[index] ?? 0
  }));
  const ceiling = Math.max(...rows.map((row) => Math.max(row.observed, row.threshold)));
  return /* @__PURE__ */ jsx3("div", { className: "scree", children: rows.map((row) => {
    const margin = row.threshold ? (row.observed - row.threshold) / row.threshold : 0;
    const state = margin <= 0 ? "below" : margin >= CLEAR_MARGIN ? "clear" : "marginal";
    return /* @__PURE__ */ jsxs3("div", { className: `scree-row ${state}`, children: [
      /* @__PURE__ */ jsx3("span", { className: "scree-index", children: row.index }),
      /* @__PURE__ */ jsxs3("div", { className: "scree-track", children: [
        /* @__PURE__ */ jsx3("i", { className: "scree-bar", style: { inlineSize: `${row.observed / ceiling * 100}%` } }),
        /* @__PURE__ */ jsx3("u", { className: "scree-null", style: { insetInlineStart: `${row.threshold / ceiling * 100}%` } })
      ] }),
      /* @__PURE__ */ jsx3("span", { className: "scree-margin", children: pct(margin) })
    ] }, row.index);
  }) });
}
function Factor({ factor, reading }) {
  const [open, setOpen] = React3.useState(false);
  const clear = isClear(factor);
  return /* @__PURE__ */ jsxs3("li", { className: `factor ${clear ? "clear" : "marginal"} ${factor.coherent === false ? "incoherent" : ""}`, children: [
    /* @__PURE__ */ jsxs3("button", { type: "button", className: "factor-head", onClick: () => setOpen(!open), "aria-expanded": open, children: [
      /* @__PURE__ */ jsx3("span", { className: "factor-name", children: factor.name }),
      /* @__PURE__ */ jsxs3("span", { className: "factor-meta", children: [
        factor.n_items,
        " propositions",
        factor.margin != null && /* @__PURE__ */ jsxs3(Fragment3, { children: [
          " \xB7 ",
          /* @__PURE__ */ jsx3("b", { children: pct(factor.margin) }),
          " over chance"
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsx3("p", { className: "factor-question", children: factor.question }),
    factor.coherent === false && /* @__PURE__ */ jsx3("p", { className: "factor-warning", children: "The namer would not call this coherent: the same films answer these together with no obvious shared question. Kept, not hidden \u2014 that is a result." }),
    open && /* @__PURE__ */ jsxs3("div", { className: "factor-detail", children: [
      /* @__PURE__ */ jsxs3("p", { className: "factor-pole low", children: [
        /* @__PURE__ */ jsxs3("b", { children: [
          "\u2212\xA0",
          factor.pole_low_label
        ] }),
        " ",
        factor.pole_low
      ] }),
      /* @__PURE__ */ jsxs3("p", { className: "factor-pole high", children: [
        /* @__PURE__ */ jsxs3("b", { children: [
          "+\xA0",
          factor.pole_high_label
        ] }),
        " ",
        factor.pole_high
      ] }),
      /* @__PURE__ */ jsx3(
        FactorDistribution,
        {
          films: factor.distribution,
          reading,
          factorId: factor.factor_id,
          poleLow: factor.pole_low_label,
          poleHigh: factor.pole_high_label
        }
      ),
      /* @__PURE__ */ jsx3(
        FilmAnchors,
        {
          high: factor.high,
          low: factor.low,
          reading,
          factorId: factor.factor_id,
          poleHigh: factor.pole_high,
          poleLow: factor.pole_low,
          highLabel: factor.pole_high_label,
          lowLabel: factor.pole_low_label
        }
      ),
      /* @__PURE__ */ jsx3("p", { className: "atlas-note", children: "Tap any film to read the propositions it answered on this axis." }),
      /* @__PURE__ */ jsx3("p", { className: "factor-examples-label", children: "The propositions this axis is made of. Films answered them together \u2014 that is the axis. The name is only a description." }),
      /* @__PURE__ */ jsx3(
        FactorPropositions,
        {
          propositions: factor.propositions,
          poleHigh: factor.pole_high_label,
          poleLow: factor.pole_low_label
        }
      )
    ] })
  ] });
}
function Factors({ data }) {
  if (!data) return null;
  const named = data.factors || [];
  const shown2 = named.length;
  const bar = Math.round((data.margin_floor ?? CLEAR_MARGIN) * 100);
  return /* @__PURE__ */ jsxs3(Fragment3, { children: [
    /* @__PURE__ */ jsxs3("section", { "aria-labelledby": "how-many", children: [
      /* @__PURE__ */ jsxs3("h2", { id: "how-many", children: [
        shown2 === 1 ? "One axis" : `${shown2} axes`,
        ", and where they came from"
      ] }),
      /* @__PURE__ */ jsxs3("p", { className: "atlas-note", children: [
        "Nobody chose these, or how many. ",
        data.scorer,
        " wrote its own propositions from",
        " ",
        data.films,
        " films' dialogue and scored the films against them; a group is the propositions the same films answer the same way. Names came last, so each describes a finished result rather than a theory the propositions were sorted into."
      ] }),
      /* @__PURE__ */ jsxs3("p", { className: "factor-headline", children: [
        /* @__PURE__ */ jsx3("b", { children: shown2 }),
        " ",
        shown2 === 1 ? "factor beats" : "factors beat",
        " chance by more than ",
        bar,
        "%, and all of them are here",
        /* @__PURE__ */ jsxs3("span", { className: "factor-headline-sub", children: [
          data.films,
          " films \xD7 ",
          data.items,
          " propositions",
          data.unanimous_items ? `, after ${data.unanimous_items} every film agreed with were set aside` : "",
          " ",
          "\xB7 at most ",
          data.max_recoverable,
          " recoverable from this many films"
        ] })
      ] }),
      !!data.unanimous_items && /* @__PURE__ */ jsxs3("p", { className: "atlas-note", children: [
        /* @__PURE__ */ jsx3("b", { children: "Propositions every film agrees with are set aside first" }),
        " \u2014",
        " ",
        data.unanimous_items,
        " here. A claim nobody argues with cannot tell two films apart, and worse, invents a dimension: each film is judged against its own affirm rate, which turns a unanimously affirmed item into a negated copy of how agreeable that film is. Those items correlated \u22121.00 with affirm rate and carried three times the weight of everything else. Removing them cut 20 axes to ",
        shown2,
        " and made what remains more reproducible, not less."
      ] }),
      !!(data.replication || []).length && /* @__PURE__ */ jsxs3(Fragment3, { children: [
        /* @__PURE__ */ jsxs3("p", { className: "atlas-note", children: [
          /* @__PURE__ */ jsx3("b", { children: "Beating chance is not the same as being real." }),
          " The test below asks whether a factor beats what the margins give away free in ",
          /* @__PURE__ */ jsx3("em", { children: "this" }),
          " corpus. A stricter test: split the films in half at random and run the analysis separately on each. Most factors pass the first test and fail this one."
        ] }),
        /* @__PURE__ */ jsx3("ul", { className: "replication", children: data.replication.map((row) => /* @__PURE__ */ jsxs3("li", { children: [
          /* @__PURE__ */ jsx3("b", { children: row.overlap.toFixed(2) }),
          /* @__PURE__ */ jsx3("span", { children: row.k === 1 ? "the strongest factor alone" : `the strongest ${row.k} together` }),
          /* @__PURE__ */ jsxs3("i", { children: [
            "chance ",
            row.chance.toFixed(3)
          ] })
        ] }, row.k)) }),
        /* @__PURE__ */ jsxs3("p", { className: "atlas-note", children: [
          "1.00 would mean the two halves found the same thing exactly. The first factor is the one that clearly survives; by the third the halves are agreeing much less, which is why the compass shows three axes and not all ",
          shown2,
          ". This is a lower bound \u2014 each half has half the films, and the estimator weakens as films are removed \u2014 so read the gap from chance rather than the number itself."
        ] })
      ] }),
      /* @__PURE__ */ jsx3("p", { className: "atlas-note", children: "A factor is kept only if it beats the 95th percentile of a null that shuffles each proposition's own answers, leaving how often it is engaged and affirmed untouched. So it has to explain more than the margins hand out free. Everything that passes is here; the app shows only the strongest few." }),
      /* @__PURE__ */ jsx3(Scree, { eigenvalues: data.eigenvalues, thresholds: data.null_threshold }),
      !!(data.adjusted_null_test?.eigenvalues || []).length && /* @__PURE__ */ jsxs3(Fragment3, { children: [
        /* @__PURE__ */ jsxs3("p", { className: "atlas-note", children: [
          /* @__PURE__ */ jsx3("b", { children: "And the same test with taste taken out." }),
          " Every proposition's verdicts are replaced with what remains once a film's taste position is subtracted, and the whole test is run again. The bars fall \u2014 the leading factor was partly taste \u2014 and more of the smaller factors clear the line, because the largest one is no longer crowding them."
        ] }),
        /* @__PURE__ */ jsx3(
          Scree,
          {
            eigenvalues: data.adjusted_null_test.eigenvalues,
            thresholds: data.adjusted_null_test.null_threshold
          }
        ),
        /* @__PURE__ */ jsxs3("p", { className: "atlas-note", children: [
          "Read against the ",
          data.adjusted_null_test.films,
          " films that have a taste position, not the ",
          data.films,
          " above \u2014 those same films with taste left in give a leading eigenvalue of",
          " ",
          /* @__PURE__ */ jsx3("b", { children: (data.adjusted_null_test.control_eigenvalues?.[0] ?? 0).toFixed(1) }),
          ", against ",
          /* @__PURE__ */ jsx3("b", { children: (data.adjusted_null_test.eigenvalues[0] ?? 0).toFixed(1) }),
          " here. That pair is the comparison; the chart above uses a larger corpus."
        ] })
      ] }),
      /* @__PURE__ */ jsxs3("p", { className: "atlas-note", children: [
        /* @__PURE__ */ jsx3("b", { children: "How silence is handled." }),
        " A film's verdict is recorded only for the propositions it takes a position on, and two propositions are compared over the films that answered ",
        /* @__PURE__ */ jsx3("em", { children: "both" }),
        " \u2014 so what is measured is agreement, not which films raise the same subjects. Each film is judged against its own affirm rate too: the scorers say \u201Caffirms\u201D far more often than \u201Cdenies\u201D. Counting silence as an answer instead made the biggest axis how talkative a film is."
      ] }),
      /* @__PURE__ */ jsxs3("p", { className: "atlas-note", children: [
        /* @__PURE__ */ jsx3("b", { children: "Where this is weakest." }),
        " This holds while silence is a property of films \u2014 some argue about more things than others \u2014 rather than scattered at random. An assumption the count rests on, not something it proves."
      ] })
    ] }),
    /* @__PURE__ */ jsxs3("section", { "aria-labelledby": "axes", children: [
      /* @__PURE__ */ jsxs3("h2", { id: "axes", children: [
        "The axes ",
        data.scorer,
        " found"
      ] }),
      named.length ? /* @__PURE__ */ jsx3("ul", { className: "factors", children: named.map((factor) => /* @__PURE__ */ jsx3(
        Factor,
        {
          factor,
          reading: {
            scorer: data.scorer,
            variant: data.variant,
            bank_version: data.bank_version
          }
        },
        factor.factor_id
      )) }) : (
        // Nothing found is a result, and it has a cause worth printing. The old
        // message here guessed that the naming step had not been run, which for
        // a scorer that HAS been through it reads as a missing chore rather
        // than as the finding it is.
        /* @__PURE__ */ jsxs3("p", { className: "atlas-note", children: [
          /* @__PURE__ */ jsx3("b", { children: "No axes." }),
          " Nothing ",
          data.scorer,
          " produced beat chance, so there is nothing to name. It scored ",
          data.films,
          " films but engaged only ",
          data.items,
          " propositions \u2014",
          " ",
          Math.round(data.density * 100),
          "% of the grid \u2014 and two propositions can only be compared over the films that answered both. At this density most pairs share barely a film, so there is almost nothing to correlate. That is a shortage of scoring rather than a verdict on the model's opinions."
        ] })
      )
    ] })
  ] });
}
var pct, Factors_default;
var init_Factors = __esm({
  "src/components/atlas/Factors.jsx"() {
    init_FactorDistribution();
    init_factorService();
    pct = (value) => `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
    Factors_default = Factors;
  }
});

// src/components/atlas/polePalette.js
function tint(hex, amount = 0.5) {
  const n = parseInt(hex.slice(1), 16);
  const mix = (c, t) => Math.round(c + (t - c) * amount);
  return `rgb(${mix(n >> 16 & 255, 245)}, ${mix(n >> 8 & 255, 239)}, ${mix(n & 255, 230)})`;
}
function polePair(family, index) {
  if (family === "taste") {
    const hue = TASTE_HUES[index % TASTE_HUES.length];
    return { low: tint(hue), high: hue };
  }
  return MORAL[index % MORAL.length];
}
function poleColour(family, index, side) {
  return polePair(family, index)[side === "low" ? "low" : "high"];
}
var MORAL, TASTE_HUES;
var init_polePalette = __esm({
  "src/components/atlas/polePalette.js"() {
    MORAL = [
      { low: "#9b7fd4", high: "#eda36b" },
      { low: "#e0797f", high: "#5cc3c0" },
      { low: "#8fbf6a", high: "#6f9fe0" }
    ];
    TASTE_HUES = ["#d96ba0", "#c9a227", "#4fa3d1", "#63c9a0", "#a86bd9"];
  }
});

// src/components/atlas/AxisScale.jsx
import React4 from "react";
import { jsx as jsx4, jsxs as jsxs4 } from "react/jsx-runtime";
function AxisScale({ low, high, value, family = "moral", index = 0 }) {
  const at = Math.max(-1, Math.min(1, value ?? 0));
  const side = at >= 0 ? "high" : "low";
  const pair = polePair(family, index);
  return /* @__PURE__ */ jsxs4(
    "span",
    {
      className: `axis-scale ${family} ${side}`,
      style: { "--low": pair.low, "--high": pair.high },
      children: [
        /* @__PURE__ */ jsxs4("span", { className: "axis-scale-poles", children: [
          /* @__PURE__ */ jsx4("em", { className: side === "low" ? "lit" : "", children: low }),
          /* @__PURE__ */ jsx4("em", { className: side === "high" ? "lit" : "", children: high })
        ] }),
        /* @__PURE__ */ jsxs4("span", { className: "axis-scale-track", children: [
          /* @__PURE__ */ jsx4("u", { className: "axis-scale-mid" }),
          /* @__PURE__ */ jsx4(
            "i",
            {
              className: `axis-scale-bar ${side}`,
              style: at >= 0 ? { insetInlineStart: "50%", inlineSize: `${Math.abs(at) * 50}%` } : { insetInlineEnd: "50%", inlineSize: `${Math.abs(at) * 50}%` }
            }
          )
        ] })
      ]
    }
  );
}
var init_AxisScale = __esm({
  "src/components/atlas/AxisScale.jsx"() {
    init_polePalette();
  }
});

// src/components/atlas/FilmTaste.jsx
import React5 from "react";
import { jsx as jsx5, jsxs as jsxs5 } from "react/jsx-runtime";
function FilmTaste({ taste, filmId }) {
  const rows = React5.useMemo(() => {
    const dims = (taste?.dimensions || []).filter((d) => d.status === "named").slice().sort((a, b) => (b.profile_reliability ?? 0) - (a.profile_reliability ?? 0)).slice(0, SHOWN);
    const films = taste?.films || [];
    if (!dims.length || !films.length) return [];
    const mine = films.find((f) => f.film_id === filmId);
    if (!mine) return [];
    return dims.map((d) => {
      const key = String(d.dim_id);
      const all = films.map((f) => f.position?.[key]).filter((v) => typeof v === "number");
      const here = mine.position?.[key];
      if (typeof here !== "number" || all.length < 20) return null;
      const mean = all.reduce((t, v) => t + v, 0) / all.length;
      const sd = Math.sqrt(all.reduce((t, v) => t + (v - mean) ** 2, 0) / all.length);
      return { dim: d, value: sd > 0 ? (here - mean) / (sd * 3) : 0 };
    }).filter(Boolean);
  }, [taste, filmId]);
  if (!rows.length) return null;
  return /* @__PURE__ */ jsxs5("div", { className: "detail-field film-taste", children: [
    /* @__PURE__ */ jsx5("span", { children: "And what kind of film it is" }),
    /* @__PURE__ */ jsx5("p", { className: "atlas-note", children: "Discovered from which films the same people enjoy, not from anything this film says." }),
    /* @__PURE__ */ jsx5("ul", { className: "film-factors", children: rows.map(({ dim, value }, index) => /* @__PURE__ */ jsx5("li", { className: "film-factor", children: /* @__PURE__ */ jsx5(
      AxisScale,
      {
        low: dim.pole_low,
        high: dim.pole_high,
        value,
        family: "taste",
        index
      }
    ) }, dim.dim_id)) })
  ] });
}
var SHOWN;
var init_FilmTaste = __esm({
  "src/components/atlas/FilmTaste.jsx"() {
    init_AxisScale();
    SHOWN = 5;
  }
});

// src/components/atlas/FilmFactors.jsx
import React6 from "react";
import { Fragment as Fragment4, jsx as jsx6, jsxs as jsxs6 } from "react/jsx-runtime";
function Row({ factor, index }) {
  const [open, setOpen] = React6.useState(false);
  const scored = factor.score != null;
  const side = factor.score >= 0 ? "high" : "low";
  const pair = polePair("moral", index);
  return /* @__PURE__ */ jsxs6(
    "li",
    {
      className: scored ? `film-factor ${side}` : "film-factor absent",
      style: { "--low": pair.low, "--high": pair.high },
      children: [
        /* @__PURE__ */ jsx6(
          "button",
          {
            type: "button",
            onClick: () => scored && setOpen(!open),
            "aria-expanded": open,
            disabled: !scored,
            "aria-label": scored ? `${factor.name}. Reads as ${side === "high" ? factor.pole_high_label : factor.pole_low_label}` : `${factor.name}. This film did not raise it`,
            children: scored ? /* @__PURE__ */ jsx6(
              AxisScale,
              {
                low: factor.pole_low_label,
                high: factor.pole_high_label,
                value: factor.score,
                family: "moral",
                index
              }
            ) : /* @__PURE__ */ jsxs6("span", { className: "film-factor-scale", children: [
              /* @__PURE__ */ jsx6("em", { children: factor.pole_low_label }),
              /* @__PURE__ */ jsx6("span", { className: "film-factor-absent", children: "did not raise this" }),
              /* @__PURE__ */ jsx6("em", { children: factor.pole_high_label })
            ] })
          }
        ),
        open && /* @__PURE__ */ jsxs6("div", { className: "film-factor-why", children: [
          /* @__PURE__ */ jsxs6("div", { className: "film-factor-poles", children: [
            /* @__PURE__ */ jsxs6("p", { className: side === "low" ? "pole low here" : "pole low", children: [
              /* @__PURE__ */ jsx6("b", { children: factor.pole_low_label }),
              " ",
              factor.pole_low
            ] }),
            /* @__PURE__ */ jsxs6("p", { className: side === "high" ? "pole high here" : "pole high", children: [
              /* @__PURE__ */ jsx6("b", { children: factor.pole_high_label }),
              " ",
              factor.pole_high
            ] })
          ] }),
          /* @__PURE__ */ jsx6(
            Verdicts,
            {
              verdicts: factor.verdicts,
              poleHigh: factor.pole_high_label,
              poleLow: factor.pole_low_label
            }
          ),
          /* @__PURE__ */ jsxs6("p", { className: "film-factor-thin", children: [
            factor.score >= 0 ? "+" : "",
            factor.score.toFixed(2),
            " from ",
            factor.items,
            " ",
            "proposition",
            factor.items === 1 ? "" : "s",
            factor.items === 1 && " \u2014 as extreme as a single answer can make it, rather than a settled reading"
          ] })
        ] })
      ]
    }
  );
}
function FilmFactors({ scorer, filmId, variant = "subs", bank = "" }) {
  const [state, setState] = React6.useState({ status: "loading" });
  React6.useEffect(() => {
    if (!scorer || !filmId) return void 0;
    let live = true;
    setState({ status: "loading" });
    loadFilmAxes({ scorer, variant, bank_version: bank }, filmId).then((data) => live && setState({ status: "ready", data })).catch(() => live && setState({ status: "failed" }));
    return () => {
      live = false;
    };
  }, [scorer, filmId, variant, bank]);
  if (state.status === "loading") return /* @__PURE__ */ jsx6("p", { className: "detail-muted", children: "Reading its positions\u2026" });
  if (state.status === "failed") {
    return /* @__PURE__ */ jsx6("p", { className: "detail-muted", children: "No axis positions for this film yet." });
  }
  const all = state.data.factors || [];
  const flagged = all.filter((factor) => factor.product);
  const factors = flagged.length ? flagged : all.slice(0, 2);
  const engaged = factors.filter((factor) => factor.score != null);
  return /* @__PURE__ */ jsxs6("div", { className: "detail-field", children: [
    /* @__PURE__ */ jsxs6("span", { children: [
      "Where ",
      state.data.scorer,
      " places it"
    ] }),
    engaged.length === 0 ? /* @__PURE__ */ jsx6("p", { className: "detail-muted", children: "Scored, but it engaged too few propositions to place on any axis." }) : /* @__PURE__ */ jsxs6(Fragment4, { children: [
      /* @__PURE__ */ jsx6("ul", { className: "film-factors", children: factors.map((factor, index) => /* @__PURE__ */ jsx6(Row, { factor, index }, factor.factor_id)) }),
      /* @__PURE__ */ jsxs6("p", { className: "atlas-note", children: [
        "Tap an axis for the propositions behind it.",
        engaged.length < factors.length && ` This film raised ${engaged.length} of ${factors.length}.`
      ] })
    ] })
  ] });
}
var FilmFactors_default;
var init_FilmFactors = __esm({
  "src/components/atlas/FilmFactors.jsx"() {
    init_AxisScale();
    init_polePalette();
    init_Verdicts();
    init_factorService();
    FilmFactors_default = FilmFactors;
  }
});

// src/services/atlasService.js
async function fetchJson(path, timeoutMs) {
  const controller = timeoutMs ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
  let response;
  try {
    response = await fetch(path, {
      headers: { Accept: "application/json" },
      signal: controller?.signal
    });
  } finally {
    if (timer) clearTimeout(timer);
  }
  if (!response.ok) throw new Error(`${path} responded ${response.status}`);
  const body = await response.json();
  if (!body || !Array.isArray(body.films)) throw new Error(`${path} is not the atlas dataset`);
  return body;
}
async function loadAtlas() {
  try {
    return await fetchJson(LIVE_PATH);
  } catch (cause) {
    throw new Error(
      "The atlas API is not answering. Start it with `uvicorn moral_atlas.web.app:app`, or check the runner \u2014 this page reads the store directly and has no cached copy to fall back to.",
      { cause }
    );
  }
}
async function loadFilmEvidence(filmId) {
  const id = encodeURIComponent(filmId);
  const response = await fetch(`/api/atlas/films/${id}`, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error("No source text is available for this film.");
  const body = await response.json();
  if (!Array.isArray(body?.layers)) throw new Error("No source text is available for this film.");
  return body;
}
function plotAxes(factors) {
  const all = factors?.factors || factors || [];
  const flagged = all.filter((f) => f && f.product);
  return flagged.length >= 2 ? flagged : all;
}
function axisPair(axes, pair) {
  const list = axes || [];
  if (list.length < 2) return list;
  if (!pair) return list.slice(0, 2);
  const find = (id) => list.find((f) => f.factor_id === id);
  const x = find(pair[0]) || list[0];
  const y = find(pair[1]) || list.find((f) => f !== x) || list[1];
  return x === y ? list.slice(0, 2) : [x, y];
}
function filmPositions(factors, space = "moral", pair = null) {
  const list = axisPair(plotAxes(factors), pair);
  const out = /* @__PURE__ */ new Map();
  if (list.length < 2) return out;
  list.forEach((factor, k) => {
    for (const row of factor.distribution || []) {
      const seen = out.get(row.film_id) || [];
      seen[k] = space === "adjusted" ? row.score_adjusted : row.score;
      out.set(row.film_id, seen);
    }
  });
  for (const [id, v] of out) {
    if (v.length !== 2 || v.some((n) => typeof n !== "number")) out.delete(id);
  }
  return out;
}
function setCentroid(positions, filmIds) {
  const found = (filmIds || []).map((id) => positions.get(id)).filter(Boolean);
  if (!found.length) return null;
  const width = Math.min(...found.map((v) => v.length));
  const mean = Array.from(
    { length: width },
    (_, k) => found.reduce((a, v) => a + v[k], 0) / found.length
  );
  return { mean, n: found.length };
}
function tasteAxes(taste) {
  return (taste?.dimensions || []).filter((d) => d.status === "named").slice().sort((a, b) => (b.profile_reliability ?? 0) - (a.profile_reliability ?? 0));
}
function planePoints(factors, taste, space = "moral", pair = null) {
  if (space === "taste") {
    const dims = tasteAxes(taste);
    if (dims.length < 2) return null;
    const at = (id, fallback) => {
      const found = dims.findIndex((d) => d.dim_id === id);
      return found < 0 ? fallback : found;
    };
    const xi = at(pair?.[0], 0);
    const yi = at(pair?.[1], xi === 1 ? 0 : 1);
    const dx = dims[xi];
    const dy = dims[yi];
    const points2 = (taste.films || []).flatMap((f) => {
      const x = f.position?.[String(dx.dim_id)];
      const y = f.position?.[String(dy.dim_id)];
      return typeof x === "number" && typeof y === "number" ? [{ id: f.film_id, title: f.title, x, y }] : [];
    });
    return {
      points: points2,
      xAxis: { high: dx.pole_high, low: dx.pole_low },
      yAxis: { high: dy.pole_high, low: dy.pole_low },
      // Which dimensions these are, in the order the palette indexes by, so the
      // plot's pole labels take the same colours the side panel gives the same
      // dimensions. They disagreed because the plot took the first two by
      // VARIANCE and the panel the first five by how well each places a person.
      index: [xi, yi]
    };
  }
  const list = axisPair(plotAxes(factors), pair);
  if (list.length < 2) return null;
  const byFilm = /* @__PURE__ */ new Map();
  list.forEach((factor, k) => {
    for (const row of factor.distribution || []) {
      const seen = byFilm.get(row.film_id) || { title: row.title, v: [] };
      seen.v[k] = space === "adjusted" ? row.score_adjusted : row.score;
      byFilm.set(row.film_id, seen);
    }
  });
  const points = [...byFilm.entries()].filter(([, f]) => f.v.length === 2 && f.v.every((n) => typeof n === "number")).map(([id, f]) => ({ id, title: f.title, x: f.v[0], y: f.v[1] }));
  const qualify = (text) => space === "adjusted" && text ? `${text}, beyond taste` : text;
  const label = (f, end) => qualify(f?.[`pole_${end}_label`] || f?.name || "");
  return {
    points,
    xAxis: { high: label(list[0], "high"), low: label(list[0], "low") },
    yAxis: { high: label(list[1], "high"), low: label(list[1], "low") }
  };
}
var LIVE_PATH;
var init_atlasService = __esm({
  "src/services/atlasService.js"() {
    LIVE_PATH = "/api/atlas";
  }
});

// src/components/atlas/FilmDetail.jsx
import React7 from "react";
import { jsx as jsx7, jsxs as jsxs7 } from "react/jsx-runtime";
function FilmDetail({ film, scorer, variant, bank, taste, onClose }) {
  const [state, setState] = React7.useState({ status: "loading" });
  React7.useEffect(() => {
    if (!film) return void 0;
    let live = true;
    setState({ status: "loading" });
    loadFilmEvidence(film.id).then((document) => live && setState({ status: "ready", document })).catch((error) => live && setState({ status: "failed", message: error.message }));
    return () => {
      live = false;
    };
  }, [film]);
  if (!film) return null;
  return /* @__PURE__ */ jsxs7("aside", { className: "film-detail", "aria-label": `${film.title} in full`, children: [
    /* @__PURE__ */ jsxs7("div", { className: "detail-head", children: [
      /* @__PURE__ */ jsxs7("div", { children: [
        /* @__PURE__ */ jsxs7("h3", { children: [
          film.title,
          " ",
          /* @__PURE__ */ jsx7("span", { children: film.year })
        ] }),
        /* @__PURE__ */ jsx7("p", { className: "detail-provenance", children: "Scored from this film's own dialogue." })
      ] }),
      /* @__PURE__ */ jsx7("button", { type: "button", className: "close-button", onClick: onClose, "aria-label": "Close", children: "\xD7" })
    ] }),
    film.description && /* @__PURE__ */ jsx7("p", { className: "detail-blurb", children: film.description }),
    scorer && /* @__PURE__ */ jsx7(
      FilmFactors_default,
      {
        scorer,
        filmId: film.id,
        variant,
        bank
      }
    ),
    state.status === "loading" && /* @__PURE__ */ jsx7("p", { className: "detail-muted", children: "Fetching the source text\u2026" }),
    state.status === "failed" && /* @__PURE__ */ jsx7("p", { className: "detail-muted", children: state.message }),
    state.status === "ready" && /* @__PURE__ */ jsxs7("div", { className: "detail-field evidence", children: [
      /* @__PURE__ */ jsx7("span", { children: "Read from" }),
      (state.document.layers || []).filter((layer) => layer.layer === variant || /dialogue|subtitle|subs/i.test(`${layer.layer} ${layer.label}`)).map((layer) => /* @__PURE__ */ jsxs7("details", { children: [
        /* @__PURE__ */ jsxs7("summary", { children: [
          layer.label,
          /* @__PURE__ */ jsx7("em", { children: layer.words ? `${layer.words.toLocaleString()} words` : "" })
        ] }),
        layer.source_url && /* @__PURE__ */ jsx7("a", { className: "evidence-source", href: layer.source_url, target: "_blank", rel: "noreferrer", children: layer.source_url }),
        /* @__PURE__ */ jsx7("pre", { children: layer.content })
      ] }, layer.layer))
    ] }),
    /* @__PURE__ */ jsx7(FilmTaste, { taste, filmId: film.id })
  ] });
}
var FilmDetail_default;
var init_FilmDetail = __esm({
  "src/components/atlas/FilmDetail.jsx"() {
    init_FilmTaste();
    init_FilmFactors();
    init_atlasService();
    FilmDetail_default = FilmDetail;
  }
});

// src/components/atlas/FilmPlane.jsx
import React8 from "react";
import { Fragment as Fragment5, jsx as jsx8, jsxs as jsxs8 } from "react/jsx-runtime";
function brighter(hex, amount = 0.45) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  const mix = (c) => Math.round(c + (255 - c) * amount);
  return `rgb(${mix(n >> 16 & 255)}, ${mix(n >> 8 & 255)}, ${mix(n & 255)})`;
}
function extent(values) {
  let lo = Infinity;
  let hi = -Infinity;
  for (const v of values) {
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  if (!Number.isFinite(lo)) return [-1, 1];
  const pad = (hi - lo) * 0.06 || 1;
  return [lo - pad, hi + pad];
}
function clampView(v) {
  const w = Math.min(SIZE, Math.max(SIZE / MAX_ZOOM, v.w));
  return {
    w,
    x: Math.min(Math.max(v.x, 0), SIZE - w),
    y: Math.min(Math.max(v.y, 0), SIZE - w)
  };
}
function FilmPlane({
  points,
  xAxis,
  yAxis,
  sets,
  viewer,
  onSelect,
  selectedId,
  matchIds,
  space = "moral",
  family = "moral",
  pairIndex = [0, 1]
}) {
  const AXIS_COLOUR = [
    poleColour(family, pairIndex[0], "high"),
    poleColour(family, pairIndex[1], "high")
  ];
  const POLE = {
    xLow: poleColour(family, pairIndex[0], "low"),
    xHigh: AXIS_COLOUR[0],
    yLow: poleColour(family, pairIndex[1], "low"),
    yHigh: AXIS_COLOUR[1]
  };
  const [hover, setHover] = React8.useState(null);
  const box = React8.useRef(null);
  const svgRef = React8.useRef(null);
  const [narrow, setNarrow] = React8.useState(false);
  React8.useEffect(() => {
    const el = box.current;
    if (!el || typeof ResizeObserver === "undefined") return void 0;
    const watch = new ResizeObserver(([entry]) => {
      setNarrow(entry.contentRect.width < 520);
    });
    watch.observe(el);
    return () => watch.disconnect();
  }, []);
  const PAD = narrow ? PAD_NARROW : PAD_WIDE;
  const [view, setView] = React8.useState(FIT);
  const viewRef = React8.useRef(view);
  viewRef.current = view;
  const zoom = SIZE / view.w;
  const zoomed = zoom > 1.001;
  const planeStyle = { "--z": zoom };
  const toPlot = React8.useCallback((clientX, clientY) => {
    const rect = svgRef.current?.getBoundingClientRect();
    const v = viewRef.current;
    if (!rect || !rect.width) return { x: v.x, y: v.y };
    return {
      x: v.x + (clientX - rect.left) / rect.width * v.w,
      y: v.y + (clientY - rect.top) / rect.height * v.w
    };
  }, []);
  const zoomAbout = React8.useCallback((factor, clientX, clientY) => {
    setView((v) => {
      const rect = svgRef.current?.getBoundingClientRect();
      const w = Math.min(SIZE, Math.max(SIZE / MAX_ZOOM, v.w / factor));
      if (!rect || !rect.width) return clampView({ ...v, w });
      const fx = (clientX - rect.left) / rect.width;
      const fy = (clientY - rect.top) / rect.height;
      return clampView({ w, x: v.x + (v.w - w) * fx, y: v.y + (v.w - w) * fy });
    });
  }, []);
  const nudge = (factor) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    zoomAbout(factor, rect.left + rect.width / 2, rect.top + rect.height / 2);
  };
  const touches = React8.useRef(/* @__PURE__ */ new Map());
  const pinch = React8.useRef(null);
  const drag = React8.useRef(null);
  const moved = React8.useRef(false);
  React8.useEffect(() => {
    const el = svgRef.current;
    if (!el) return void 0;
    const spread = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
    const mid = (t) => [(t[0].clientX + t[1].clientX) / 2, (t[0].clientY + t[1].clientY) / 2];
    const onStart = (e) => {
      moved.current = false;
      if (e.touches.length === 2) {
        e.preventDefault();
        pinch.current = { dist: spread(e.touches) };
        drag.current = null;
      } else if (e.touches.length === 1 && SIZE / viewRef.current.w > 1.001) {
        drag.current = toPlot(e.touches[0].clientX, e.touches[0].clientY);
      }
    };
    const onMove = (e) => {
      if (e.touches.length >= 2) {
        e.preventDefault();
        const dist = spread(e.touches);
        if (pinch.current?.dist > 0 && dist > 0) {
          moved.current = true;
          const [mx, my] = mid(e.touches);
          zoomAbout(dist / pinch.current.dist, mx, my);
        }
        pinch.current = { dist };
        return;
      }
      if (drag.current && e.touches.length === 1) {
        e.preventDefault();
        const at = toPlot(e.touches[0].clientX, e.touches[0].clientY);
        const dx = at.x - drag.current.x;
        const dy = at.y - drag.current.y;
        if (Math.abs(dx) > 1 || Math.abs(dy) > 1) moved.current = true;
        setView((v) => clampView({ ...v, x: v.x - dx, y: v.y - dy }));
      }
    };
    const onEnd = (e) => {
      if (e.touches.length < 2) pinch.current = null;
      if (e.touches.length === 0) drag.current = null;
    };
    el.addEventListener("touchstart", onStart, { passive: false });
    el.addEventListener("touchmove", onMove, { passive: false });
    el.addEventListener("touchend", onEnd);
    el.addEventListener("touchcancel", onEnd);
    return () => {
      el.removeEventListener("touchstart", onStart);
      el.removeEventListener("touchmove", onMove);
      el.removeEventListener("touchend", onEnd);
      el.removeEventListener("touchcancel", onEnd);
    };
  }, [toPlot, zoomAbout]);
  const down = (e) => {
    if (e.pointerType === "touch") return;
    touches.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    moved.current = false;
    if (zoomed) {
      drag.current = toPlot(e.clientX, e.clientY);
      e.currentTarget.setPointerCapture?.(e.pointerId);
    }
  };
  const move = (e) => {
    if (e.pointerType === "touch" || !touches.current.has(e.pointerId)) return;
    if (!drag.current) return;
    const at = toPlot(e.clientX, e.clientY);
    const dx = at.x - drag.current.x;
    const dy = at.y - drag.current.y;
    if (Math.abs(dx) > 1 || Math.abs(dy) > 1) moved.current = true;
    setView((v) => clampView({ ...v, x: v.x - dx, y: v.y - dy }));
  };
  const up = (e) => {
    if (e.pointerType === "touch") return;
    touches.current.delete(e.pointerId);
    if (touches.current.size === 0) drag.current = null;
  };
  const { placed, cx, cy, centroids } = React8.useMemo(() => {
    if (!points || points.length < 2) return { placed: [], centroids: [] };
    const [x0, x1] = extent(points.map((p) => p.x));
    const [y0, y1] = extent(points.map((p) => p.y));
    const sx = (v) => PAD + (v - x0) / (x1 - x0) * (SIZE - PAD * 2);
    const sy = (v) => SIZE - PAD - (v - y0) / (y1 - y0) * (SIZE - PAD * 2);
    const colour = {};
    for (const s of sets || []) for (const id of s.films || []) colour[id] = s.colour;
    const placedPoints = points.map((p) => ({
      ...p,
      px: sx(p.x),
      py: sy(p.y),
      colour: colour[p.id]
    }));
    const marks = (sets || []).map((s) => {
      const mine = placedPoints.filter((p) => (s.films || []).includes(p.id));
      if (mine.length < 3) return null;
      return {
        name: s.name,
        colour: brighter(s.colour),
        n: mine.length,
        px: mine.reduce((a, p) => a + p.px, 0) / mine.length,
        py: mine.reduce((a, p) => a + p.py, 0) / mine.length
      };
    }).filter(Boolean);
    return {
      placed: placedPoints,
      centroids: marks,
      cx: sx(0) > PAD && sx(0) < SIZE - PAD ? sx(0) : null,
      cy: sy(0) > PAD && sy(0) < SIZE - PAD ? sy(0) : null
    };
  }, [points, sets, PAD]);
  if (!placed.length) return null;
  const me = viewer && placed.find((p) => p.id === viewer.id);
  const highlighting = centroids.length > 0 || (sets || []).some((s) => (s.films || []).length > 0);
  const out = (px, py) => ({ x: (px - view.x) * zoom, y: (py - view.y) * zoom });
  return /* @__PURE__ */ jsxs8(
    "figure",
    {
      className: `film-plane${narrow ? " narrow" : ""}${highlighting ? " has-set" : ""}` + (zoomed ? " zoomed" : ""),
      style: planeStyle,
      ref: box,
      children: [
        /* @__PURE__ */ jsxs8(
          "svg",
          {
            ref: svgRef,
            viewBox: `0 0 ${SIZE} ${SIZE}`,
            role: "img",
            style: { touchAction: zoomed ? "none" : "pan-y" },
            onPointerDown: down,
            onPointerMove: move,
            onPointerUp: up,
            onPointerCancel: up,
            onPointerLeave: up,
            onDoubleClick: (e) => zoomAbout(1.8, e.clientX, e.clientY),
            "aria-label": `${points.length} films placed on ${xAxis.high} against ${yAxis.high}`,
            children: [
              /* @__PURE__ */ jsxs8("g", { transform: `scale(${zoom}) translate(${-view.x} ${-view.y})`, children: [
                cy != null && /* @__PURE__ */ jsx8(
                  "line",
                  {
                    className: "plane-rule",
                    style: { stroke: AXIS_COLOUR[0] },
                    x1: PAD - 10,
                    y1: cy,
                    x2: SIZE - PAD + 10,
                    y2: cy
                  }
                ),
                cx != null && /* @__PURE__ */ jsx8(
                  "line",
                  {
                    className: "plane-rule",
                    style: { stroke: AXIS_COLOUR[1] },
                    x1: cx,
                    y1: PAD - 10,
                    x2: cx,
                    y2: SIZE - PAD + 10
                  }
                ),
                placed.map((p) => {
                  const matched = matchIds ? matchIds.has(p.id) : false;
                  const base = narrow ? 4.2 : 2.6;
                  const r = p.id === selectedId ? base + 3 : matched ? base + 2 : base;
                  return /* @__PURE__ */ jsxs8(
                    "g",
                    {
                      className: `plane-mark${p.colour ? " in-set" : ""}` + (matched ? " matched" : "") + (p.id === selectedId ? " chosen" : ""),
                      style: p.colour ? { stroke: p.colour } : void 0,
                      onMouseEnter: () => setHover(p),
                      onMouseLeave: () => setHover((h) => h && h.id === p.id ? null : h),
                      onClick: () => {
                        if (!moved.current && onSelect) onSelect(p.id);
                      },
                      children: [
                        /* @__PURE__ */ jsx8("path", { d: `M${p.px - r} ${p.py}H${p.px + r}M${p.px} ${p.py - r}V${p.py + r}` }),
                        /* @__PURE__ */ jsx8("circle", { className: "plane-hit", cx: p.px, cy: p.py, r: "7" }),
                        /* @__PURE__ */ jsx8("title", { children: p.title })
                      ]
                    },
                    p.id
                  );
                })
              ] }),
              centroids.map((c) => {
                const at = out(c.px, c.py);
                if (at.x < 0 || at.y < 0 || at.x > SIZE || at.y > SIZE) return null;
                const arms = [[0, -1], [0, 1], [-1, 0], [1, 0]];
                const flip = at.x > SIZE - 150;
                return /* @__PURE__ */ jsxs8("g", { className: "plane-centre", children: [
                  /* @__PURE__ */ jsxs8("g", { className: "halo", children: [
                    /* @__PURE__ */ jsx8("circle", { cx: at.x, cy: at.y, r: "10" }),
                    arms.map(([ax, ay]) => /* @__PURE__ */ jsx8(
                      "line",
                      {
                        x1: at.x + ax * 14,
                        y1: at.y + ay * 14,
                        x2: at.x + ax * 23,
                        y2: at.y + ay * 23
                      },
                      `h${ax}${ay}`
                    ))
                  ] }),
                  /* @__PURE__ */ jsxs8("g", { style: { stroke: c.colour }, children: [
                    /* @__PURE__ */ jsx8("circle", { cx: at.x, cy: at.y, r: "10" }),
                    arms.map(([ax, ay]) => /* @__PURE__ */ jsx8(
                      "line",
                      {
                        x1: at.x + ax * 14,
                        y1: at.y + ay * 14,
                        x2: at.x + ax * 23,
                        y2: at.y + ay * 23
                      },
                      `${ax}${ay}`
                    ))
                  ] }),
                  /* @__PURE__ */ jsx8("circle", { className: "core", cx: at.x, cy: at.y, r: "3", style: { fill: c.colour } }),
                  /* @__PURE__ */ jsxs8(
                    "text",
                    {
                      className: "plane-centre-label",
                      style: { fill: c.colour },
                      x: at.x + (flip ? -27 : 27),
                      y: at.y + 4,
                      textAnchor: flip ? "end" : "start",
                      children: [
                        c.name,
                        " ",
                        /* @__PURE__ */ jsxs8("tspan", { className: "n", children: [
                          "(",
                          c.n,
                          ")"
                        ] })
                      ]
                    }
                  )
                ] }, c.name);
              }),
              me && (() => {
                const at = out(me.px, me.py);
                return /* @__PURE__ */ jsx8("circle", { className: "plane-you", cx: at.x, cy: at.y, r: "6.5" });
              })(),
              /* @__PURE__ */ jsx8(
                "text",
                {
                  className: "plane-pole",
                  style: { fill: POLE.yHigh },
                  x: SIZE / 2,
                  y: PAD - 14,
                  textAnchor: "middle",
                  children: yAxis.high
                }
              ),
              /* @__PURE__ */ jsx8(
                "text",
                {
                  className: "plane-pole",
                  style: { fill: POLE.yLow },
                  x: SIZE / 2,
                  y: SIZE - PAD + 24,
                  textAnchor: "middle",
                  children: yAxis.low
                }
              ),
              /* @__PURE__ */ jsx8(
                "text",
                {
                  className: "plane-pole",
                  style: { fill: POLE.xHigh },
                  x: SIZE - PAD + 8,
                  y: SIZE / 2 - 7,
                  textAnchor: "end",
                  children: xAxis.high
                }
              ),
              /* @__PURE__ */ jsx8(
                "text",
                {
                  className: "plane-pole",
                  style: { fill: POLE.xLow },
                  x: PAD - 8,
                  y: SIZE / 2 - 7,
                  textAnchor: "start",
                  children: xAxis.low
                }
              )
            ]
          }
        ),
        /* @__PURE__ */ jsxs8("div", { className: "plane-zoom", children: [
          /* @__PURE__ */ jsx8(
            "button",
            {
              type: "button",
              onClick: () => nudge(1 / 1.6),
              disabled: !zoomed,
              "aria-label": "Zoom out",
              children: "\u2212"
            }
          ),
          /* @__PURE__ */ jsx8(
            "button",
            {
              type: "button",
              onClick: () => nudge(1.6),
              disabled: zoom >= MAX_ZOOM - 1e-3,
              "aria-label": "Zoom in",
              children: "+"
            }
          ),
          /* @__PURE__ */ jsx8(
            "button",
            {
              type: "button",
              className: "plane-zoom-reset",
              onClick: () => setView(FIT),
              disabled: !zoomed,
              children: "Fit"
            }
          ),
          /* @__PURE__ */ jsxs8("span", { "aria-hidden": "true", children: [
            zoom.toFixed(1),
            "\xD7"
          ] })
        ] }),
        /* @__PURE__ */ jsx8("figcaption", { children: hover ? /* @__PURE__ */ jsx8("b", { children: hover.title }) : /* @__PURE__ */ jsxs8(Fragment5, { children: [
          placed.length,
          " films, ",
          CAPTION[space] || CAPTION.moral,
          highlighting ? " Ringed crosshairs mark the centre of each highlighted list." : " Pinch, scroll with ctrl held, or double-tap to zoom in."
        ] }) })
      ]
    }
  );
}
var SIZE, PAD_WIDE, PAD_NARROW, MAX_ZOOM, FIT, CAPTION;
var init_FilmPlane = __esm({
  "src/components/atlas/FilmPlane.jsx"() {
    init_polePalette();
    SIZE = 600;
    PAD_WIDE = 46;
    PAD_NARROW = 62;
    MAX_ZOOM = 6;
    FIT = { x: 0, y: 0, w: SIZE };
    CAPTION = {
      moral: "placed by what their dialogue argues.",
      taste: "placed by which films the same people enjoy.",
      adjusted: "placed by what their dialogue argues once the part taste predicts is removed \u2014 so a film sits where it is MORE than its taste explains."
    };
  }
});

// src/components/atlas/FilmExplorer.jsx
import React9 from "react";
import { Fragment as Fragment6, jsx as jsx9, jsxs as jsxs9 } from "react/jsx-runtime";
function FilmExplorer({
  films,
  factors,
  taste,
  reading,
  selectedId,
  onSelect,
  sets,
  viewer,
  space = "moral",
  onSpaceChange,
  pair = null,
  onPairChange,
  axes = []
}) {
  const [query, setQuery] = React9.useState("");
  const shown2 = React9.useMemo(() => axisPair(axes, pair), [axes, pair]);
  const choices = React9.useMemo(() => space === "taste" ? tasteAxes(taste).map((d) => ({ id: d.dim_id, low: d.pole_low, high: d.pole_high })) : axes.map((a) => ({ id: a.factor_id, low: a.pole_low_label, high: a.pole_high_label })), [space, taste, axes]);
  const current = React9.useMemo(() => {
    if (space !== "taste") return [shown2[0]?.factor_id, shown2[1]?.factor_id];
    const ids = choices.map((c) => c.id);
    const x = ids.includes(pair?.[0]) ? pair[0] : ids[0];
    const y = ids.includes(pair?.[1]) && pair[1] !== x ? pair[1] : ids.find((i) => i !== x);
    return [x, y];
  }, [space, choices, pair, shown2]);
  const panel = React9.useRef(null);
  const choose = React9.useCallback((id) => {
    onSelect(id);
    if (!id) return;
    setQuery("");
    window.requestAnimationFrame(() => {
      const el = panel.current;
      if (el && window.matchMedia("(max-width: 900px)").matches) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  }, [onSelect]);
  const plane = React9.useMemo(
    () => planePoints(factors, taste, space, pair),
    [factors, taste, space, pair]
  );
  const all = films || [];
  const matches = React9.useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return [];
    return all.filter((f) => `${f.title} ${f.year ?? ""}`.toLowerCase().includes(needle));
  }, [all, query]);
  const matchIds = React9.useMemo(
    () => matches.length ? new Set(matches.map((f) => f.id)) : null,
    [matches]
  );
  const selected = all.find((f) => f.id === selectedId);
  const point = plane?.points.find((p) => p.id === selectedId);
  const listed = !plane && matches.length ? matches.slice(0, 40) : [];
  const title = selected?.title || point?.title;
  return /* @__PURE__ */ jsxs9("section", { className: plane ? "film-explorer" : "film-explorer no-plot", children: [
    /* @__PURE__ */ jsxs9("div", { className: "explorer-plot", children: [
      onSpaceChange && /* @__PURE__ */ jsxs9("div", { className: "plane-axis-pick", role: "tablist", "aria-label": "Which axes to plot", children: [
        /* @__PURE__ */ jsx9(
          "button",
          {
            type: "button",
            role: "tab",
            "aria-selected": space === "moral",
            className: space === "moral" ? "on" : void 0,
            onClick: () => onSpaceChange("moral"),
            children: "What films argue"
          }
        ),
        /* @__PURE__ */ jsx9(
          "button",
          {
            type: "button",
            role: "tab",
            "aria-selected": space === "taste",
            className: space === "taste" ? "on" : void 0,
            onClick: () => onSpaceChange("taste"),
            children: "What people choose by"
          }
        ),
        /* @__PURE__ */ jsx9(
          "button",
          {
            type: "button",
            role: "tab",
            "aria-selected": space === "adjusted",
            className: space === "adjusted" ? "on" : void 0,
            onClick: () => onSpaceChange("adjusted"),
            children: "What they argue, taste removed"
          }
        )
      ] }),
      onPairChange && choices.length > 2 && /* @__PURE__ */ jsx9("div", { className: "plane-pair", children: [["across", 0], ["up", 1]].map(([label, slot]) => /* @__PURE__ */ jsxs9("label", { children: [
        /* @__PURE__ */ jsx9("span", { children: label }),
        /* @__PURE__ */ jsx9(
          "select",
          {
            value: current[slot] ?? "",
            onChange: (e) => onPairChange(slot === 0 ? [Number(e.target.value), current[1]] : [current[0], Number(e.target.value)]),
            children: choices.map((c) => /* @__PURE__ */ jsxs9("option", { value: c.id, disabled: c.id === current[1 - slot], children: [
              c.low,
              " \u2013 ",
              c.high
            ] }, c.id))
          }
        )
      ] }, label)) }),
      /* @__PURE__ */ jsx9(
        "input",
        {
          className: "atlas-search",
          value: query,
          placeholder: "Search for a film",
          "aria-label": "Search for a film",
          onChange: (event) => setQuery(event.target.value)
        }
      ),
      listed.length > 0 && /* @__PURE__ */ jsx9("ul", { className: "film-list", children: listed.map((f) => /* @__PURE__ */ jsx9("li", { children: /* @__PURE__ */ jsxs9("button", { type: "button", onClick: () => choose(f.id), children: [
        /* @__PURE__ */ jsx9("b", { children: f.title }),
        " ",
        /* @__PURE__ */ jsx9("span", { children: f.year })
      ] }) }, f.id)) }),
      query.trim() && /* @__PURE__ */ jsx9("p", { className: "atlas-note explorer-matches", children: matches.length ? /* @__PURE__ */ jsxs9(Fragment6, { children: [
        matches.length,
        " highlighted",
        matches.length <= 8 && " \u2014 ",
        matches.length <= 8 && matches.map((f, i) => /* @__PURE__ */ jsxs9(React9.Fragment, { children: [
          i > 0 && ", ",
          /* @__PURE__ */ jsx9(
            "button",
            {
              type: "button",
              className: "link-button",
              onClick: () => choose(f.id),
              children: f.title
            }
          )
        ] }, f.id))
      ] }) : /* @__PURE__ */ jsxs9(Fragment6, { children: [
        "Nothing matches \u201C",
        query.trim(),
        "\u201D. The corpus is ",
        all.length,
        " films, so plenty of cinema is not in it yet."
      ] }) }),
      plane && /* @__PURE__ */ jsx9(
        FilmPlane,
        {
          space,
          points: plane.points,
          xAxis: plane.xAxis,
          yAxis: plane.yAxis,
          family: space === "taste" ? "taste" : "moral",
          pairIndex: plane.index || [
            axes.findIndex((a) => a.factor_id === shown2[0]?.factor_id),
            axes.findIndex((a) => a.factor_id === shown2[1]?.factor_id)
          ].map((i) => i < 0 ? 0 : i),
          sets,
          viewer: space === "moral" ? viewer : null,
          selectedId,
          matchIds,
          onSelect: choose
        }
      )
    ] }),
    /* @__PURE__ */ jsx9("div", { className: "explorer-panel", ref: panel, children: title ? (
      // FilmDetail already carries the axes, the taste position and the
      // dialogue a claim was read from. Rendering its parts again here put
      // every axis on the screen twice.
      /* @__PURE__ */ jsx9(
        FilmDetail_default,
        {
          film: selected || { id: selectedId, title },
          scorer: reading?.scorer,
          variant: reading?.variant,
          bank: reading?.bank_version,
          taste,
          onClose: () => onSelect(null)
        }
      )
    ) : /* @__PURE__ */ jsx9("p", { className: "atlas-note explorer-empty", children: "Every dot is one film, placed by what its dialogue argues. Films near each other make similar moral claims." }) })
  ] });
}
var init_FilmExplorer = __esm({
  "src/components/atlas/FilmExplorer.jsx"() {
    init_FilmDetail();
    init_FilmPlane();
    init_atlasService();
  }
});

// src/components/atlas/AxisAdjustment.jsx
import React10 from "react";
import { Fragment as Fragment7, jsx as jsx10, jsxs as jsxs10 } from "react/jsx-runtime";
function num(found, key) {
  const f = found?.[key];
  return f ? f.display ?? f.value : null;
}
function AxisAdjustment({ data, taste }) {
  const axes = data?.factors || [];
  const found = taste?.findings;
  if (!axes.length) return null;
  const measured = data?.bank_version === MEASURED_ON;
  const anyAdjusted = axes.some((f) => typeof f.taste_explained === "number");
  const anyPlaced = axes.some((f) => typeof f.places_people === "boolean");
  const anyCoherence = axes.some((f) => typeof f.coherence === "number");
  if (!anyAdjusted && !anyPlaced && !anyCoherence) return null;
  const dropped = axes.filter((f) => f.places_people === false);
  return /* @__PURE__ */ jsxs10("section", { className: "axis-adjust", "aria-labelledby": "adjust", children: [
    /* @__PURE__ */ jsx10("h2", { id: "adjust", children: "The axes, before and after taste is taken out" }),
    /* @__PURE__ */ jsx10("p", { children: "Every moral position on this page has had the part predictable from taste removed. How much that is differs enormously by axis." }),
    /* @__PURE__ */ jsx10("div", { className: "table-scroll", children: /* @__PURE__ */ jsxs10("table", { className: "figures", children: [
      /* @__PURE__ */ jsx10("thead", { children: /* @__PURE__ */ jsxs10("tr", { children: [
        /* @__PURE__ */ jsx10("th", { children: "Axis" }),
        /* @__PURE__ */ jsx10("th", { children: "Taste explained" }),
        anyCoherence && /* @__PURE__ */ jsx10("th", { children: "Own propositions agree" }),
        measured && /* @__PURE__ */ jsx10("th", { children: "Ideologies separate" }),
        anyPlaced && /* @__PURE__ */ jsx10("th", { children: "A person can be placed" })
      ] }) }),
      /* @__PURE__ */ jsx10("tbody", { children: axes.map((f, i) => {
        const fails = f.places_people === false;
        return /* @__PURE__ */ jsxs10("tr", { className: fails ? "axis-dropped" : "lead", children: [
          /* @__PURE__ */ jsxs10("td", { children: [
            f.name,
            fails && /* @__PURE__ */ jsx10("small", { children: " \u2014 measured, not plotted" })
          ] }),
          /* @__PURE__ */ jsx10("td", { className: "n", children: typeof f.taste_explained === "number" ? `${(f.taste_explained * 100).toFixed(0)}%` : "\u2014" }),
          anyCoherence && /* @__PURE__ */ jsx10("td", { className: "n", children: typeof f.coherence === "number" ? f.coherence.toFixed(2) : "\u2014" }),
          measured && /* @__PURE__ */ jsx10("td", { className: "n", children: num(found, `axis${i + 1}_separation`) ? `F = ${num(found, `axis${i + 1}_separation`)}` : "\u2014" }),
          anyPlaced && /* @__PURE__ */ jsx10("td", { className: "n", children: typeof f.person_reliability === "number" ? `${f.person_reliability.toFixed(2)} / ${f.person_ceiling.toFixed(2)}` : "\u2014" })
        ] }, f.dim_id ?? f.factor_id ?? i);
      }) })
    ] }) }),
    anyPlaced && /* @__PURE__ */ jsxs10("p", { className: "atlas-note", children: [
      "Placement is read as the figure against its own noise ceiling \u2014 the second number, which differs by axis because it depends on how many people rated films that axis separates. An axis clears when the first exceeds the second. Agreement is the mean correlation between a factor's own propositions across the films that answered both, with each pair's sign turned to face the axis \u2014 two propositions stating opposite ends of one idea correlate negatively and agree completely.",
      measured && /* @__PURE__ */ jsxs10(Fragment7, { children: [
        " Separation is compared against the F that shuffling the films produces,",
        " ",
        num(found, "separation_null") ?? "\u2014",
        "."
      ] })
    ] }),
    dropped.length > 0 && /* @__PURE__ */ jsxs10("div", { className: "note open", children: [
      /* @__PURE__ */ jsxs10("h3", { children: [
        "Why ",
        dropped.length === 1 ? "an axis is" : "some axes are",
        " measured but not plotted"
      ] }),
      /* @__PURE__ */ jsxs10("p", { children: [
        dropped.map((f) => f.name).join(", "),
        " groups propositions that genuinely go together, but a person's position on it cannot be told from noise. A real grouping with no demonstrated validity is not a moral dimension. It stays visible here \u2014 this is an audit page \u2014 but nothing is plotted or recommended from it."
      ] })
    ] }),
    measured && dropped.length === 0 && /* @__PURE__ */ jsxs10("div", { className: "note open", children: [
      /* @__PURE__ */ jsx10("h3", { children: "All three are plotted, and one of them nearly was not" }),
      /* @__PURE__ */ jsxs10("p", { children: [
        "Autonomy vs Order was withdrawn once, on an earlier reading where no ideological list separated along it and a person could not be placed on it above noise. Under the common-factor extraction it passes both \u2014 it separates the lists at",
        " ",
        "F = ",
        num(found, "axis3_separation") ?? "\u2014",
        " against",
        " ",
        num(found, "separation_null") ?? "\u2014",
        " from shuffled films, and places a person better than either of the other two."
      ] }),
      /* @__PURE__ */ jsxs10("p", { className: "atlas-note", children: [
        "The second axis stays the awkward one, and is published anyway: its propositions are the ",
        /* @__PURE__ */ jsx10("em", { children: "least" }),
        " coherent of the three, yet it separates ideological lists and a person can be placed on it. Most likely correctly identified and badly delimited."
      ] })
    ] })
  ] });
}
var MEASURED_ON;
var init_AxisAdjustment = __esm({
  "src/components/atlas/AxisAdjustment.jsx"() {
    MEASURED_ON = "dolphin-subs";
  }
});

// src/services/apiClient.js
async function request(path, options = {}, attempt = 0) {
  const method = options.method || "GET";
  const requestBody = options.body ? JSON.parse(options.body) : void 0;
  if (requestBody) console.info(`[Something Good To Watch API] ${method} ${path} request
${JSON.stringify(requestBody, null, 2)}`);
  let response;
  try {
    response = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", ...options.headers }
    });
  } catch (networkError) {
    console.error(`[Something Good To Watch API] ${method} ${path} never reached the server`, networkError);
    if (REPEATABLE.has(method) && attempt === 0) return request(path, options, attempt + 1);
    throw new Error("That did not reach the server. Check your connection and try again.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    console.error(`[Something Good To Watch API] ${method} ${path} failed ${response.status}
${JSON.stringify(body, null, 2)}`);
    if (TRANSIENT.has(response.status) && REPEATABLE.has(method) && attempt === 0) {
      return request(path, options, attempt + 1);
    }
    const detail = Array.isArray(body?.detail) ? body.detail[0]?.msg : body?.detail;
    if (detail) throw new Error(detail);
    throw new Error(TRANSIENT.has(response.status) ? `The connection to the service dropped (${response.status}). Please try again.` : `The service could not complete that request (${response.status}).`);
  }
  console.info(`[Something Good To Watch API] ${method} ${path} response
${JSON.stringify(body, null, 2)}`);
  return body;
}
var REPEATABLE, TRANSIENT, apiClient;
var init_apiClient = __esm({
  "src/services/apiClient.js"() {
    REPEATABLE = /* @__PURE__ */ new Set(["GET", "HEAD"]);
    TRANSIENT = /* @__PURE__ */ new Set([502, 503, 504]);
    apiClient = {
      get: (path, options) => request(path, options),
      post: (path, body, options = {}) => request(path, { ...options, method: "POST", body: JSON.stringify(body) })
    };
  }
});

// src/services/profileService.js
function loadMoralProfile(access) {
  return apiClient.get("/api/profile/moral", {
    headers: { "X-Session-Token": access.token }
  });
}
function loadSessionMoralProfiles(access, shareToken) {
  return apiClient.get(`/api/profile/moral/session/${encodeURIComponent(shareToken)}`, {
    headers: { "X-Session-Token": access.token }
  });
}
var init_profileService = __esm({
  "src/services/profileService.js"() {
    init_apiClient();
  }
});

// src/styles/atlas.css
var init_atlas = __esm({
  "src/styles/atlas.css"() {
  }
});

// src/screens/AtlasPage.jsx
var AtlasPage_exports = {};
__export(AtlasPage_exports, {
  default: () => AtlasPage_default
});
import React11 from "react";
import { Fragment as Fragment8, jsx as jsx11, jsxs as jsxs11 } from "react/jsx-runtime";
function filmParam() {
  const [, search = ""] = window.location.hash.split("?");
  return new URLSearchParams(search).get("film");
}
function AtlasPage({ onBack, access }) {
  const [models, setModels] = React11.useState(null);
  const [selected, setSelected] = React11.useState(null);
  const [factors, setFactors] = React11.useState(null);
  const [filmSets, setFilmSets] = React11.useState([]);
  const [activeSets, setActiveSets] = React11.useState(() => /* @__PURE__ */ new Set());
  const [allSets, setAllSets] = React11.useState(false);
  const [factorsError, setFactorsError] = React11.useState(null);
  const [corpus, setCorpus] = React11.useState(null);
  const [selectedId, setSelectedId] = React11.useState(filmParam);
  const [taste, setTaste] = React11.useState(null);
  const [space, setSpace] = React11.useState("moral");
  const [pair, setPair] = React11.useState(null);
  React11.useEffect(() => {
    let live = true;
    loadFilmSets().then((p) => live && setFilmSets(p.sets || [])).catch(() => {
    });
    loadTaste().then((t) => live && setTaste(t)).catch(() => {
    });
    return () => {
      live = false;
    };
  }, []);
  const SET_ORDER = [
    "christian-answers",
    "catholic",
    "christian-edifying",
    "conservative",
    "red-pilled",
    "church-of-satan",
    "progressive-canon",
    "feminist",
    "glaad-lgbtq",
    "naacp-antiracist",
    "socialist",
    "old-hollywood",
    "new-hollywood",
    "blockbuster-hollywood",
    "franchise-hollywood",
    "mcu"
  ];
  const SHORTLIST = ["christian-answers", "progressive-canon", "red-pilled"];
  const orderedSets = React11.useMemo(() => {
    const rank = (s) => {
      const at = SET_ORDER.indexOf(s.set_id);
      return at === -1 ? SET_ORDER.length : at;
    };
    return [...filmSets].sort((a, b) => rank(a) - rank(b));
  }, [filmSets]);
  const chosen = React11.useMemo(
    () => orderedSets.filter((s) => activeSets.has(s.set_id)),
    [orderedSets, activeSets]
  );
  const productAxes = React11.useMemo(() => plotAxes(factors), [factors]);
  const shownAxes = React11.useMemo(() => axisPair(productAxes, pair), [productAxes, pair]);
  const centres = React11.useMemo(() => {
    const positions = filmPositions(factors, space, pair);
    const out = {};
    for (const s of chosen) out[s.set_id] = setCentroid(positions, s.films);
    return out;
  }, [factors, chosen, space, pair]);
  const [viewer, setViewer] = React11.useState(null);
  const viewerHere = React11.useMemo(() => {
    if (!viewer || (viewer.scores?.length || 0) < 2) return null;
    if (viewer.dim_version !== selected?.scorer) return null;
    if (viewer.bank_version !== selected?.bank_version) return null;
    return { scores: viewer.scores.map((s) => s.score), label: "You" };
  }, [viewer, selected]);
  const wantsMe = (window.location.hash.split("?")[1] || "").includes("me=1");
  React11.useEffect(() => {
    if (!wantsMe || !access) return void 0;
    let live = true;
    loadMoralProfile(access).then((p) => live && setViewer(p)).catch(() => {
    });
    return () => {
      live = false;
    };
  }, [wantsMe, access]);
  React11.useEffect(() => {
    let live = true;
    loadModels().then(({ models: found }) => {
      if (!live) return;
      setModels(found);
      if (found.length) setSelected(found.find((m) => m.product) || found[0]);
    }).catch(() => live && setModels([]));
    loadAtlas().then((payload) => live && setCorpus(payload)).catch(() => {
    });
    return () => {
      live = false;
    };
  }, []);
  React11.useEffect(() => {
    if (!selected) return void 0;
    let live = true;
    setFactors(null);
    setFactorsError(null);
    loadFactors(selected.scorer, selected.variant, selected.bank_version).then((payload) => live && setFactors(payload)).catch((error) => live && setFactorsError(error.message));
    return () => {
      live = false;
    };
  }, [selected]);
  React11.useEffect(() => {
    const onHash = () => setSelectedId(filmParam());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  if (models === null) {
    return /* @__PURE__ */ jsx11("main", { className: "app-page", children: /* @__PURE__ */ jsx11("p", { className: "message", children: "Reading the atlas\u2026" }) });
  }
  return /* @__PURE__ */ jsx11("main", { className: "atlas-page", children: /* @__PURE__ */ jsxs11("div", { className: "atlas-wrap", children: [
    /* @__PURE__ */ jsxs11("header", { className: "atlas-header", children: [
      onBack && /* @__PURE__ */ jsx11("button", { type: "button", className: "back-button", onClick: onBack, children: "\u2190" }),
      /* @__PURE__ */ jsxs11("div", { children: [
        /* @__PURE__ */ jsx11("h1", { children: "What do these films argue?" }),
        /* @__PURE__ */ jsx11("p", { className: "atlas-note", children: "Films answer moral propositions written from their own dialogue, and an axis is a set of propositions films answer together. Nobody chose them, or how many there are." })
      ] })
    ] }),
    !models.length ? /* @__PURE__ */ jsx11("section", { children: /* @__PURE__ */ jsxs11("p", { className: "atlas-note", children: [
      "No model has scored the corpus yet. Run ",
      /* @__PURE__ */ jsx11("code", { children: "atlas model-propose" }),
      ",",
      " ",
      /* @__PURE__ */ jsx11("code", { children: "atlas model-bank" }),
      ", ",
      /* @__PURE__ */ jsx11("code", { children: "atlas model-scan" }),
      " and",
      " ",
      /* @__PURE__ */ jsx11("code", { children: "atlas name-factors" }),
      "."
    ] }) }) : /* @__PURE__ */ jsxs11(Fragment8, { children: [
      /* @__PURE__ */ jsxs11("p", { className: "atlas-note taste-pointer", children: [
        "These axes are what films ",
        /* @__PURE__ */ jsx11("em", { children: "argue" }),
        ". What people choose by is a different set of dimensions, and the harder test of these \u2014 ",
        /* @__PURE__ */ jsx11(
          "a",
          {
            className: "link-button",
            href: "#/taste",
            children: "the taste dimensions \u2192"
          }
        )
      ] }),
      factorsError && /* @__PURE__ */ jsx11("p", { className: "atlas-note", children: factorsError }),
      !factors && !factorsError && /* @__PURE__ */ jsxs11("p", { className: "message", children: [
        "Reading ",
        selected?.scorer,
        "\u2026"
      ] }),
      factors?.factors?.length >= 2 && /* @__PURE__ */ jsxs11(Fragment8, { children: [
        filmSets.length > 0 && /* @__PURE__ */ jsxs11("div", { className: "set-picker", children: [
          /* @__PURE__ */ jsx11("span", { className: "set-picker-label", children: "highlight a set" }),
          orderedSets.filter((s) => allSets || SHORTLIST.includes(s.set_id) || activeSets.has(s.set_id)).map((s) => /* @__PURE__ */ jsxs11("span", { className: "set-chip-wrap", children: [
            /* @__PURE__ */ jsxs11(
              "button",
              {
                type: "button",
                className: `set-chip${activeSets.has(s.set_id) ? " on" : ""}`,
                style: activeSets.has(s.set_id) ? { borderColor: s.colour, color: s.colour } : void 0,
                "aria-pressed": activeSets.has(s.set_id),
                "aria-describedby": `set-tip-${s.set_id}`,
                title: s.source || void 0,
                onClick: () => setActiveSets((prev) => {
                  const next = new Set(prev);
                  next.has(s.set_id) ? next.delete(s.set_id) : next.add(s.set_id);
                  return next;
                }),
                children: [
                  /* @__PURE__ */ jsx11("i", { style: { background: s.colour } }),
                  s.name,
                  /* @__PURE__ */ jsx11("small", { children: s.n })
                ]
              }
            ),
            /* @__PURE__ */ jsxs11("span", { className: "set-tip", id: `set-tip-${s.set_id}`, role: "tooltip", children: [
              /* @__PURE__ */ jsx11("b", { style: { color: s.colour }, children: s.name }),
              /* @__PURE__ */ jsx11("span", { className: "set-tip-desc", children: s.description }),
              /* @__PURE__ */ jsx11("span", { className: "set-tip-src", children: s.url ? /* @__PURE__ */ jsx11("a", { href: s.url, target: "_blank", rel: "noreferrer noopener", children: s.source }) : s.source }),
              /* @__PURE__ */ jsxs11("span", { className: "set-tip-n", children: [
                s.n,
                " of its films are in the corpus.",
                centres[s.set_id] && space !== "taste" && /* @__PURE__ */ jsxs11(Fragment8, { children: [
                  " ",
                  "Centre ",
                  centres[s.set_id].mean.slice(0, shownAxes.length).map((m) => `${m >= 0 ? "+" : "\u2212"}${Math.abs(m).toFixed(3)}`).join(" / "),
                  " on ",
                  shownAxes.map((f) => f.name).join(", "),
                  "."
                ] })
              ] })
            ] })
          ] }, s.set_id)),
          /* @__PURE__ */ jsx11(
            "button",
            {
              type: "button",
              className: "set-more",
              "aria-expanded": allSets,
              onClick: () => setAllSets((v) => !v),
              children: allSets ? "fewer sets" : `more sets (${orderedSets.filter((s) => !SHORTLIST.includes(s.set_id)).length})`
            }
          )
        ] }),
        /* @__PURE__ */ jsx11(
          FilmExplorer,
          {
            films: corpus?.films || [],
            factors,
            taste,
            reading: selected,
            selectedId,
            onSelect: setSelectedId,
            sets: chosen,
            viewer: viewerHere,
            space,
            onSpaceChange: setSpace,
            pair,
            onPairChange: setPair,
            axes: productAxes
          }
        ),
        wantsMe && !viewerHere && /* @__PURE__ */ jsx11("p", { className: "atlas-note", children: !access ? "Take the survey first and this will show where you sit." : !viewer ? "Reading your compass\u2026" : `Your compass was measured against the ${viewer.dim_version} reading, so it cannot be placed on this one. Switch the reading above to see yourself.` })
      ] }),
      /* @__PURE__ */ jsx11(AxisAdjustment, { data: factors, taste }),
      /* @__PURE__ */ jsx11(Factors_default, { data: factors })
    ] })
  ] }) });
}
var AtlasPage_default;
var init_AtlasPage = __esm({
  "src/screens/AtlasPage.jsx"() {
    init_Factors();
    init_FilmExplorer();
    init_AxisAdjustment();
    init_atlasService();
    init_profileService();
    init_factorService();
    init_atlas();
    AtlasPage_default = AtlasPage;
  }
});

// src/components/compass/TasteRead.jsx
import React12 from "react";
import { Fragment as Fragment9, jsx as jsx12, jsxs as jsxs12 } from "react/jsx-runtime";
function lean(percentile) {
  const distance = Math.abs(percentile - 50);
  if (distance < 8) return "right in the middle";
  if (distance < 20) return "leans";
  if (distance < 35) return "clearly";
  return "strongly";
}
function TasteRead({ taste, companions = [] }) {
  const rows = (taste || []).slice(0, SHOWN2);
  if (!rows.length) return null;
  return /* @__PURE__ */ jsxs12("section", { className: "taste-read", children: [
    /* @__PURE__ */ jsx12("h2", { className: "taste-read-head", children: "What you are drawn to" }),
    /* @__PURE__ */ jsx12("ul", { className: "taste-axes", children: rows.map((row, index) => {
      const high = row.percentile >= 50;
      const label = high ? row.pole_high : row.pole_low;
      const strength = lean(row.percentile);
      const others = companions.map((c) => ({
        name: c.name,
        row: (c.profile?.taste || []).find((t) => t.dim_id === row.dim_id)
      })).filter((c) => c.row);
      return /* @__PURE__ */ jsxs12("li", { className: "taste-axis", style: { "--hue": HUES[index % HUES.length] }, children: [
        /* @__PURE__ */ jsx12("p", { className: "taste-axis-read", children: strength === "right in the middle" ? /* @__PURE__ */ jsxs12(Fragment9, { children: [
          "You sit ",
          /* @__PURE__ */ jsxs12("b", { children: [
            "between ",
            row.pole_low.toLowerCase(),
            " and ",
            row.pole_high.toLowerCase()
          ] }),
          "."
        ] }) : /* @__PURE__ */ jsxs12(Fragment9, { children: [
          "You ",
          strength === "leans" ? "lean toward" : "",
          strength === "clearly" ? "clearly prefer" : "",
          strength === "strongly" ? "strongly prefer" : "",
          " ",
          /* @__PURE__ */ jsx12("b", { children: label.toLowerCase() }),
          "."
        ] }) }),
        /* @__PURE__ */ jsxs12("span", { className: "taste-axis-poles", children: [
          /* @__PURE__ */ jsx12("span", { className: high ? "" : "lit", children: row.pole_low }),
          /* @__PURE__ */ jsx12("span", { className: high ? "lit" : "", children: row.pole_high })
        ] }),
        /* @__PURE__ */ jsxs12("span", { className: "taste-axis-track", children: [
          /* @__PURE__ */ jsx12("i", { className: "taste-axis-mid" }),
          /* @__PURE__ */ jsx12(
            "i",
            {
              className: "taste-axis-band",
              style: high ? { left: "50%", width: `${row.percentile - 50}%` } : { left: `${row.percentile}%`, width: `${50 - row.percentile}%` }
            }
          ),
          others.map((other) => /* @__PURE__ */ jsx12(
            "b",
            {
              className: "taste-axis-marker companion",
              style: { left: `${other.row.percentile}%` },
              title: `${other.name || "They"}: ${other.row.percentile}`
            },
            other.name || other.row.dim_id
          )),
          /* @__PURE__ */ jsx12("b", { className: "taste-axis-marker", style: { left: `${row.percentile}%` } })
        ] })
      ] }, row.dim_id);
    }) }),
    /* @__PURE__ */ jsxs12("p", { className: "taste-axes-note", children: [
      "Built from which films the same people enjoy, across 162,000 outside raters.",
      companions.length > 0 && " Hollow markers are the others in your session."
    ] })
  ] });
}
var SHOWN2, HUES;
var init_TasteRead = __esm({
  "src/components/compass/TasteRead.jsx"() {
    SHOWN2 = 5;
    HUES = ["#eda36b", "#5cc3c0", "#b58ce0", "#e0899a", "#93c56b"];
  }
});

// src/screens/CompassScreen.jsx
var CompassScreen_exports = {};
__export(CompassScreen_exports, {
  default: () => CompassScreen_default
});
import React13, { useEffect, useState } from "react";
import { jsx as jsx13, jsxs as jsxs13 } from "react/jsx-runtime";
function readingOf({ films_rated: rated, pairs_answered: pairs }) {
  const parts = [];
  if (rated) parts.push(`${rated} ${rated === 1 ? "film you know" : "films you know"}`);
  if (pairs) parts.push(`${pairs} ${pairs === 1 ? "story you chose" : "stories you chose"} blind`);
  return parts.join(" and ");
}
function CompassScreen({ access, shareToken, onContinue }) {
  const [profile, setProfile] = useState(null);
  const [companions, setCompanions] = useState([]);
  const [error, setError] = useState(null);
  useEffect(() => {
    if (!access) return;
    loadMoralProfile(access).then(setProfile).catch(() => setError("Your compass could not be loaded yet."));
  }, [access]);
  useEffect(() => {
    if (!access || !shareToken) return void 0;
    let live = true;
    loadSessionMoralProfiles(access, shareToken).then((payload) => live && setCompanions(payload.companions || [])).catch(() => live && setCompanions([]));
    return () => {
      live = false;
    };
  }, [access, shareToken]);
  if (error) return /* @__PURE__ */ jsx13("main", { className: "app-page", children: /* @__PURE__ */ jsx13("p", { className: "message", children: error }) });
  if (!profile) return /* @__PURE__ */ jsx13("main", { className: "app-page", children: /* @__PURE__ */ jsx13("p", { className: "message", children: "Reading your compass\u2026" }) });
  const reading = readingOf(profile.evidence);
  return /* @__PURE__ */ jsx13("main", { className: "app-page", children: /* @__PURE__ */ jsxs13("section", { className: "phone-screen compass-screen", children: [
    /* @__PURE__ */ jsxs13("header", { className: "compass-header", children: [
      /* @__PURE__ */ jsx13("span", { children: "Your compass" }),
      /* @__PURE__ */ jsxs13("span", { className: "compass-view-label", children: [
        profile.evidence.films_used,
        " films read"
      ] })
    ] }),
    /* @__PURE__ */ jsx13("h1", { children: "What you are drawn to." }),
    /* @__PURE__ */ jsx13("p", { className: "compass-lede", children: "Read from the films you know, against 162,000 other raters." }),
    profile.is_provisional && /* @__PURE__ */ jsx13("p", { className: "compass-provisional", children: "Still provisional \u2014 a few more films and these will settle." }),
    /* @__PURE__ */ jsx13(TasteRead, { taste: profile.taste, companions }),
    /* @__PURE__ */ jsxs13("div", { className: "compass-action", children: [
      /* @__PURE__ */ jsxs13("button", { className: "peach-button", type: "button", onClick: onContinue, children: [
        "See tonight\u2019s list ",
        /* @__PURE__ */ jsx13("span", { "aria-hidden": "true", children: "\u2192" })
      ] }),
      /* @__PURE__ */ jsx13("a", { className: "quiet-link", href: "#/corpus", children: "Look up a film you love \u2192" }),
      /* @__PURE__ */ jsx13("a", { className: "quiet-link", href: "#/atlas?me=1", children: "See where you sit among the films \u2192" }),
      /* @__PURE__ */ jsx13("a", { className: "quiet-link", href: "#/atlas", children: "Where do these scales come from? \u2192" })
    ] })
  ] }) });
}
var CompassScreen_default;
var init_CompassScreen = __esm({
  "src/screens/CompassScreen.jsx"() {
    init_TasteRead();
    init_profileService();
    CompassScreen_default = CompassScreen;
  }
});

// src/screens/CorpusPage.jsx
var CorpusPage_exports = {};
__export(CorpusPage_exports, {
  default: () => CorpusPage
});
import React14 from "react";
import { jsx as jsx14, jsxs as jsxs14 } from "react/jsx-runtime";
function CorpusPage({ onBack }) {
  const [corpus, setCorpus] = React14.useState(null);
  const [reading, setReading] = React14.useState(null);
  const [selected, setSelected] = React14.useState(null);
  const [error, setError] = React14.useState(null);
  const [space, setSpace] = React14.useState("moral");
  const [pair, setPair] = React14.useState(null);
  const [factors, setFactors] = React14.useState(null);
  const [taste, setTaste] = React14.useState(null);
  const productAxes = React14.useMemo(() => plotAxes(factors), [factors]);
  React14.useEffect(() => {
    let live = true;
    loadAtlas().then((payload) => live && setCorpus(payload)).catch((e) => live && setError(e.message));
    loadModels().then(({ models }) => {
      if (live && models.length) setReading(models.find((m) => m.product) || models[0]);
    }).catch(() => {
    });
    loadTaste().then((t) => live && setTaste(t)).catch(() => {
    });
    return () => {
      live = false;
    };
  }, []);
  React14.useEffect(() => {
    if (!reading) return void 0;
    let live = true;
    loadFactors(reading.scorer, reading.variant, reading.bank_version).then((f) => live && setFactors(f)).catch((e) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [reading]);
  const all = corpus?.films || [];
  return /* @__PURE__ */ jsxs14("main", { className: "atlas-page", children: [
    /* @__PURE__ */ jsxs14("header", { className: "atlas-header", children: [
      onBack && /* @__PURE__ */ jsx14("button", { type: "button", className: "back-button", onClick: onBack, children: "\u2190" }),
      /* @__PURE__ */ jsx14("div", { children: /* @__PURE__ */ jsx14("h1", { children: "What does it make of your film?" }) })
    ] }),
    /* @__PURE__ */ jsxs14("div", { className: "atlas-wrap", children: [
      /* @__PURE__ */ jsxs14("p", { className: "atlas-lede", children: [
        "Every film here was read from its own dialogue \u2014 no reviews, no synopsis. Search ",
        all.length ? `${all.length} films` : "the corpus",
        ", or pick a point."
      ] }),
      error && /* @__PURE__ */ jsx14("p", { className: "atlas-note", children: error }),
      /* @__PURE__ */ jsx14(
        FilmExplorer,
        {
          films: all,
          factors,
          taste,
          reading,
          selectedId: selected?.id || null,
          onSelect: (id) => setSelected(all.find((f) => f.id === id) || null),
          space,
          onSpaceChange: setSpace,
          pair,
          onPairChange: setPair,
          axes: productAxes
        }
      ),
      !selected && /* @__PURE__ */ jsx14("p", { className: "atlas-note", children: "If a film is not here it simply has not been read yet \u2014 the corpus grows by subtitle availability, not by taste." }),
      /* @__PURE__ */ jsx14("p", { className: "corpus-footer", children: /* @__PURE__ */ jsx14("a", { className: "quiet-link", href: "#/atlas", children: "Where do these scales come from? \u2192" }) })
    ] })
  ] });
}
var init_CorpusPage = __esm({
  "src/screens/CorpusPage.jsx"() {
    init_FilmExplorer();
    init_atlasService();
    init_factorService();
    init_atlas();
  }
});

// src/screens/LandingPage.jsx
var LandingPage_exports = {};
__export(LandingPage_exports, {
  default: () => LandingPage_default
});
import React15 from "react";
import { Fragment as Fragment10, jsx as jsx15, jsxs as jsxs15 } from "react/jsx-runtime";
function LandingPage({ onStart, joining = false }) {
  const [error, setError] = React15.useState(null);
  const [starting, setStarting] = React15.useState(null);
  async function begin(mode) {
    setError(null);
    setStarting(mode);
    try {
      await onStart(mode);
    } catch (startError) {
      setError(startError.message);
      setStarting(null);
    }
  }
  return /* @__PURE__ */ jsx15("main", { className: "app-page login-page", children: /* @__PURE__ */ jsxs15("section", { className: "phone-screen login-screen", "aria-label": "Start", children: [
    /* @__PURE__ */ jsxs15("div", { className: "brand", children: [
      /* @__PURE__ */ jsx15("span", { className: "brand-mark", "aria-hidden": "true", children: "\u2295" }),
      /* @__PURE__ */ jsx15("span", { children: "Something Good To Watch" })
    ] }),
    /* @__PURE__ */ jsxs15("div", { className: "login-content", children: [
      /* @__PURE__ */ jsx15("p", { className: "screen-label", children: joining ? "A friend invited you" : "90 seconds \xB7 no sign-up" }),
      /* @__PURE__ */ jsx15("h1", { children: joining ? /* @__PURE__ */ jsxs15(Fragment10, { children: [
        "Watch something",
        /* @__PURE__ */ jsx15("br", {}),
        /* @__PURE__ */ jsx15("em", { children: "together." })
      ] }) : /* @__PURE__ */ jsxs15(Fragment10, { children: [
        "Find something",
        /* @__PURE__ */ jsx15("br", {}),
        /* @__PURE__ */ jsx15("em", { children: "good" }),
        " to watch."
      ] }) }),
      /* @__PURE__ */ jsx15("p", { className: "screen-copy", children: joining ? "They are already answering. You will each answer on your own \u2014 neither of you sees the other\u2019s answers until the end." : "Every film argues for something. Spend ninety seconds on films you already know, and we will read what you believe out of what you liked \u2014 then find films that argue for it." })
    ] }),
    error && /* @__PURE__ */ jsx15("p", { className: "message", role: "alert", children: error }),
    joining ? /* @__PURE__ */ jsx15("div", { className: "start-choices", children: /* @__PURE__ */ jsx15("button", { className: "peach-button", type: "button", disabled: starting, onClick: () => begin("join"), children: starting ? "Joining\u2026" : /* @__PURE__ */ jsxs15(Fragment10, { children: [
      "Join them ",
      /* @__PURE__ */ jsx15("span", { "aria-hidden": "true", children: "\u2192" })
    ] }) }) }) : /* @__PURE__ */ jsxs15("div", { className: "start-choices", children: [
      /* @__PURE__ */ jsx15("button", { className: "peach-button", type: "button", disabled: starting, onClick: () => begin("pair"), children: starting === "pair" ? "Setting up\u2026" : /* @__PURE__ */ jsxs15(Fragment10, { children: [
        "With a friend ",
        /* @__PURE__ */ jsx15("span", { "aria-hidden": "true", children: "\u2192" })
      ] }) }),
      /* @__PURE__ */ jsxs15("button", { className: "start-secondary", type: "button", disabled: starting, onClick: () => begin("solo"), children: [
        starting === "solo" ? "Starting\u2026" : "Just me",
        /* @__PURE__ */ jsx15("small", { children: "Find out what your taste says about you" })
      ] })
    ] }),
    /* @__PURE__ */ jsxs15("p", { className: "login-footer", children: [
      joining ? "No sign-up \u2014 they are waiting for you." : "Nothing to sign up for, and no names needed.",
      /* @__PURE__ */ jsx15("br", {}),
      /* @__PURE__ */ jsx15("a", { className: "quiet-link", href: "#/corpus", children: "Look up a film \u2192" }),
      /* @__PURE__ */ jsx15("br", {}),
      /* @__PURE__ */ jsx15("a", { className: "quiet-link", href: "#/atlas", children: "See the dataset behind it \u2192" })
    ] })
  ] }) });
}
var LandingPage_default;
var init_LandingPage = __esm({
  "src/screens/LandingPage.jsx"() {
    LandingPage_default = LandingPage;
  }
});

// src/components/FilmAxisStrip.jsx
import React16 from "react";
import { jsx as jsx16, jsxs as jsxs16 } from "react/jsx-runtime";
function Axis({ factor, open, onToggle, index }) {
  const side = factor.score >= 0 ? "high" : "low";
  const pair = polePair("moral", index);
  const stance = factor.score >= 0 ? factor.pole_high : factor.pole_low;
  const magnitude = Math.abs(factor.score) * 50;
  const heaviest = Math.max(
    ...(factor.verdicts || []).map((v) => v.weight || 0),
    1e-4
  );
  return /* @__PURE__ */ jsxs16(
    "li",
    {
      className: `axis-strip-row ${side} ${open ? "open" : ""}`,
      style: { "--low": pair.low, "--high": pair.high },
      children: [
        /* @__PURE__ */ jsxs16("button", { type: "button", onClick: onToggle, "aria-expanded": open, children: [
          /* @__PURE__ */ jsxs16("span", { className: "axis-strip-name", children: [
            factor.score >= 0 ? factor.pole_high_label : factor.pole_low_label,
            /* @__PURE__ */ jsxs16("em", { children: [
              "over ",
              factor.score >= 0 ? factor.pole_low_label : factor.pole_high_label
            ] })
          ] }),
          /* @__PURE__ */ jsx16("span", { className: "axis-strip-track", children: /* @__PURE__ */ jsx16("i", { style: factor.score >= 0 ? { insetInlineStart: "50%", inlineSize: `${magnitude}%` } : { insetInlineEnd: "50%", inlineSize: `${magnitude}%` } }) })
        ] }),
        open && /* @__PURE__ */ jsxs16("div", { className: "axis-strip-why", children: [
          /* @__PURE__ */ jsx16("p", { className: "axis-strip-stance", children: stance }),
          /* @__PURE__ */ jsx16("ul", { children: (factor.verdicts || []).slice(0, 3).map((verdict) => /* @__PURE__ */ jsxs16("li", { className: verdict.verdict, children: [
            /* @__PURE__ */ jsx16("b", { children: verdict.verdict }),
            /* @__PURE__ */ jsxs16("span", { children: [
              verdict.text,
              verdict.weight != null && /* @__PURE__ */ jsx16(
                "span",
                {
                  className: "axis-strip-weight",
                  title: `How much this proposition defines this axis (loading ${verdict.weight})`,
                  children: /* @__PURE__ */ jsx16("i", { style: { inlineSize: `${Math.round(verdict.weight / heaviest * 100)}%` } })
                }
              )
            ] })
          ] }, verdict.item_id)) }),
          /* @__PURE__ */ jsxs16("p", { className: "axis-strip-count", children: [
            "read from ",
            factor.items,
            " proposition",
            factor.items === 1 ? "" : "s"
          ] })
        ] })
      ]
    }
  );
}
function FilmAxisStrip({ filmId, limit = 3, tasteLimit = 3 }) {
  const [factors, setFactors] = React16.useState(null);
  const [taste, setTaste] = React16.useState(null);
  const [openId, setOpenId] = React16.useState(null);
  React16.useEffect(() => {
    if (!filmId) return void 0;
    let live = true;
    setFactors(null);
    setOpenId(null);
    loadProductFilmAxes(filmId).then((data) => live && setFactors(shown(data.factors || [], limit))).catch(() => live && setFactors([]));
    return () => {
      live = false;
    };
  }, [filmId, limit]);
  React16.useEffect(() => {
    let live = true;
    loadTaste().then((t) => live && setTaste(t)).catch(() => live && setTaste(null));
    return () => {
      live = false;
    };
  }, []);
  const tasteRows = React16.useMemo(() => {
    const dims = (taste?.dimensions || []).filter((d) => d.status === "named").slice().sort((a, b) => (b.profile_reliability ?? 0) - (a.profile_reliability ?? 0)).slice(0, tasteLimit);
    const films = taste?.films || [];
    const mine = films.find((f) => f.film_id === filmId);
    if (!mine || !dims.length) return [];
    return dims.map((d, index) => {
      const key = String(d.dim_id);
      const all = films.map((f) => f.position?.[key]).filter((v) => typeof v === "number");
      const here = mine.position?.[key];
      if (typeof here !== "number" || all.length < 20) return null;
      const mean = all.reduce((t, v) => t + v, 0) / all.length;
      const sd = Math.sqrt(all.reduce((t, v) => t + (v - mean) ** 2, 0) / all.length);
      const at = sd > 0 ? Math.max(-1, Math.min(1, (here - mean) / (sd * 3))) : 0;
      return { dim: d, at, index };
    }).filter(Boolean);
  }, [taste, filmId, tasteLimit]);
  if (!factors?.length && !tasteRows.length) return null;
  return /* @__PURE__ */ jsxs16("div", { className: "axis-strip", children: [
    /* @__PURE__ */ jsx16("span", { className: "axis-strip-label", children: "Where it stands \xB7 tap for why" }),
    /* @__PURE__ */ jsx16("ul", { children: factors.map((factor, index) => /* @__PURE__ */ jsx16(
      Axis,
      {
        factor,
        index,
        open: openId === factor.factor_id,
        onToggle: () => setOpenId(openId === factor.factor_id ? null : factor.factor_id)
      },
      factor.factor_id
    )) }),
    tasteRows.length > 0 && /* @__PURE__ */ jsxs16("div", { className: "axis-strip-taste", children: [
      /* @__PURE__ */ jsx16("span", { className: "axis-strip-label", children: "And what kind of film" }),
      /* @__PURE__ */ jsx16("ul", { children: tasteRows.map(({ dim, at, index }) => {
        const pair = polePair("taste", index);
        const high = at >= 0;
        return /* @__PURE__ */ jsxs16("li", { style: { "--low": pair.low, "--high": pair.high }, children: [
          /* @__PURE__ */ jsxs16("span", { className: "axis-strip-name", children: [
            high ? dim.pole_high : dim.pole_low,
            /* @__PURE__ */ jsxs16("em", { children: [
              "over ",
              high ? dim.pole_low : dim.pole_high
            ] })
          ] }),
          /* @__PURE__ */ jsx16("span", { className: `axis-strip-track ${high ? "high" : "low"}`, children: /* @__PURE__ */ jsx16("i", { style: high ? { insetInlineStart: "50%", inlineSize: `${Math.abs(at) * 50}%` } : { insetInlineEnd: "50%", inlineSize: `${Math.abs(at) * 50}%` } }) })
        ] }, dim.dim_id);
      }) })
    ] })
  ] });
}
var shown;
var init_FilmAxisStrip = __esm({
  "src/components/FilmAxisStrip.jsx"() {
    init_factorService();
    init_polePalette();
    shown = (factors, limit) => factors.filter((factor) => factor.score != null && factor.items > 0).slice(0, limit);
  }
});

// src/services/shortlistService.js
function loadNextShortlistFilm(access, shareToken, since = 0) {
  return apiClient.get(`/api/shortlist/next?share_token=${encodeURIComponent(shareToken)}&since=${since}`, { headers: { "X-Session-Token": access.token } });
}
function loadShortlistSelection(access, shareToken) {
  return apiClient.get(`/api/shortlist/selection?share_token=${encodeURIComponent(shareToken)}`, { headers: { "X-Session-Token": access.token } });
}
function saveShortlistReaction(access, shareToken, filmId, reaction) {
  return apiClient.post("/api/shortlist/reactions", { share_token: shareToken, film_id: filmId, reaction }, { headers: { "X-Session-Token": access.token } });
}
var init_shortlistService = __esm({
  "src/services/shortlistService.js"() {
    init_apiClient();
  }
});

// src/screens/MatchPage.jsx
var MatchPage_exports = {};
__export(MatchPage_exports, {
  default: () => MatchPage
});
import React17, { useEffect as useEffect2, useState as useState2 } from "react";
import { jsx as jsx17, jsxs as jsxs17 } from "react/jsx-runtime";
function MatchPage({ access, shareToken, films: initial, solo = false, onKeepLooking, onStartOver }) {
  const [films, setFilms] = useState2(initial || []);
  const [openId, setOpenId] = useState2(null);
  const [error, setError] = useState2(null);
  useEffect2(() => {
    if (!access || !shareToken) return void 0;
    let active = true;
    loadShortlistSelection(access, shareToken).then((result) => {
      if (!active) return;
      if (result.state === "shortlist") setFilms(result.films);
    }).catch((requestError) => active && setError(requestError.message));
    return () => {
      active = false;
    };
  }, [access, shareToken]);
  if (!films.length) return /* @__PURE__ */ jsx17("main", { className: "app-page", children: /* @__PURE__ */ jsx17("p", { className: "message", children: "Gathering your shortlist\u2026" }) });
  return /* @__PURE__ */ jsx17("main", { className: "app-page match-page", children: /* @__PURE__ */ jsxs17("section", { className: "match-sheet", children: [
    /* @__PURE__ */ jsx17("div", { className: "sheet-handle" }),
    /* @__PURE__ */ jsxs17("p", { className: "screen-label", children: [
      /* @__PURE__ */ jsx17("i", {}),
      " ",
      /* @__PURE__ */ jsx17("i", {}),
      " ",
      solo ? "Your yeses" : "You both said yes"
    ] }),
    /* @__PURE__ */ jsxs17("h1", { children: [
      "Your ",
      /* @__PURE__ */ jsx17("em", { children: "shortlist." })
    ] }),
    /* @__PURE__ */ jsx17("p", { className: "match-lede", children: solo ? `${films.length} ${films.length === 1 ? "film" : "films"} that argue for what your taste says you believe. Pick whichever you fancy tonight.` : `${films.length} ${films.length === 1 ? "film" : "films"} you each said yes to, without seeing what the other one picked. Pick whichever you fancy tonight.` }),
    error && /* @__PURE__ */ jsx17("p", { className: "message", role: "alert", children: error }),
    /* @__PURE__ */ jsx17("ul", { className: "match-list", children: films.map((film) => /* @__PURE__ */ jsxs17("li", { className: openId === film.id ? "match-item open" : "match-item", children: [
      /* @__PURE__ */ jsxs17(
        "button",
        {
          type: "button",
          onClick: () => setOpenId(openId === film.id ? null : film.id),
          "aria-expanded": openId === film.id,
          children: [
            /* @__PURE__ */ jsx17("span", { className: "match-art", style: film.artwork_url ? { backgroundImage: `linear-gradient(0deg, rgba(23,19,16,.55), transparent), url(${film.artwork_url})` } : {}, "aria-hidden": "true" }),
            /* @__PURE__ */ jsxs17("span", { className: "match-title", children: [
              /* @__PURE__ */ jsx17("b", { children: film.title }),
              /* @__PURE__ */ jsx17("em", { children: film.year }),
              film.note && /* @__PURE__ */ jsx17("small", { children: film.note })
            ] })
          ]
        }
      ),
      openId === film.id && /* @__PURE__ */ jsxs17("div", { className: "match-detail", children: [
        film.description && /* @__PURE__ */ jsx17("p", { children: film.description }),
        /* @__PURE__ */ jsx17(FilmAxisStrip, { filmId: film.id }),
        /* @__PURE__ */ jsxs17(
          "a",
          {
            className: "peach-button",
            href: `https://www.justwatch.com/au/search?q=${encodeURIComponent(film.title)}`,
            target: "_blank",
            rel: "noreferrer",
            children: [
              "See where to watch ",
              /* @__PURE__ */ jsx17("span", { "aria-hidden": "true", children: "\u2197" })
            ]
          }
        )
      ] })
    ] }, film.id)) }),
    /* @__PURE__ */ jsxs17("div", { className: "match-actions", children: [
      /* @__PURE__ */ jsx17("button", { className: "match-secondary-button", type: "button", onClick: onKeepLooking, children: "Keep looking" }),
      /* @__PURE__ */ jsx17("button", { className: "match-text-button", type: "button", onClick: onStartOver, children: "Start over" }),
      /* @__PURE__ */ jsx17("a", { className: "quiet-link", href: "#/corpus", children: "Look up a film you love \u2192" }),
      /* @__PURE__ */ jsx17("a", { className: "quiet-link", href: "#/atlas", children: "Where do these scales come from? \u2192" })
    ] })
  ] }) });
}
var init_MatchPage = __esm({
  "src/screens/MatchPage.jsx"() {
    init_FilmAxisStrip();
    init_shortlistService();
  }
});

// src/components/FlowProgress.jsx
import React18 from "react";
import { jsx as jsx18, jsxs as jsxs18 } from "react/jsx-runtime";
function FlowProgress({ current, total = FLOW_STEP_COUNT, onBack, backLabel = "Previous step" }) {
  return /* @__PURE__ */ jsxs18("header", { className: "flow-progress", children: [
    /* @__PURE__ */ jsx18("button", { className: "back-button", type: "button", "aria-label": backLabel, disabled: !onBack, onClick: onBack, children: "\u2190" }),
    /* @__PURE__ */ jsx18("div", { className: "segment-progress", "aria-label": `Step ${current} of ${total}`, children: Array.from({ length: total }, (_, index) => /* @__PURE__ */ jsx18("i", { className: index < current ? "active" : "" }, index)) }),
    /* @__PURE__ */ jsxs18("span", { children: [
      current,
      " / ",
      total
    ] })
  ] });
}
var SEEN_IT_CARDS, FLOW_STEP_COUNT;
var init_FlowProgress = __esm({
  "src/components/FlowProgress.jsx"() {
    SEEN_IT_CARDS = 20;
    FLOW_STEP_COUNT = SEEN_IT_CARDS;
  }
});

// src/hooks/useSwipeDecision.js
import { useEffect as useEffect3, useRef, useState as useState3 } from "react";
function useSwipeDecision({ disabled = false, onLeft, onRight }) {
  const startRef = useRef(null);
  const offsetRef = useRef(0);
  const decisionTimerRef = useRef(null);
  const [offset, setOffset] = useState3(0);
  const [dragging, setDragging] = useState3(false);
  const [committed, setCommitted] = useState3(false);
  useEffect3(() => () => window.clearTimeout(decisionTimerRef.current), []);
  function reset() {
    startRef.current = null;
    offsetRef.current = 0;
    decisionTimerRef.current = null;
    setOffset(0);
    setDragging(false);
    setCommitted(false);
  }
  function handlePointerDown(event) {
    if (disabled || committed || decisionTimerRef.current !== null || event.button !== 0) return;
    startRef.current = { pointerId: event.pointerId, x: event.clientX };
    setDragging(true);
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }
  function handlePointerMove(event) {
    if (!startRef.current || startRef.current.pointerId !== event.pointerId) return;
    const nextOffset = Math.max(-MAX_DRAG, Math.min(MAX_DRAG, event.clientX - startRef.current.x));
    offsetRef.current = nextOffset;
    setOffset(nextOffset);
  }
  function handlePointerUp(event) {
    if (!startRef.current || startRef.current.pointerId !== event.pointerId) return;
    const finalOffset = offsetRef.current;
    const decision = finalOffset <= -SWIPE_THRESHOLD ? onLeft : finalOffset >= SWIPE_THRESHOLD ? onRight : null;
    if (decision) {
      startRef.current = null;
      setDragging(false);
      setCommitted(true);
      setOffset(finalOffset < 0 ? -EXIT_DISTANCE : EXIT_DISTANCE);
      decisionTimerRef.current = window.setTimeout(() => {
        reset();
        void decision();
      }, EXIT_DURATION_MS);
      return;
    }
    reset();
  }
  const strength = Math.min(Math.abs(offset) / SWIPE_THRESHOLD, 1);
  return {
    direction: offset < -10 ? "left" : offset > 10 ? "right" : null,
    committed,
    strength,
    style: {
      transform: `translate3d(${offset}px, 0, 0) rotate(${offset / 28}deg)`,
      transition: dragging ? "none" : void 0
    },
    handlers: {
      onPointerDown: handlePointerDown,
      onPointerMove: handlePointerMove,
      onPointerUp: handlePointerUp,
      onPointerCancel: reset
    }
  };
}
var SWIPE_THRESHOLD, MAX_DRAG, EXIT_DISTANCE, EXIT_DURATION_MS;
var init_useSwipeDecision = __esm({
  "src/hooks/useSwipeDecision.js"() {
    SWIPE_THRESHOLD = 72;
    MAX_DRAG = 140;
    EXIT_DISTANCE = 520;
    EXIT_DURATION_MS = 160;
  }
});

// src/services/movieService.js
async function loadOnboardingFilms(access, shareToken) {
  const payload = await apiClient.get(`/api/onboarding/films?share_token=${encodeURIComponent(shareToken)}`, {
    headers: { "X-Session-Token": access.token }
  });
  return payload.films;
}
function loadMoreOnboardingFilms(access, shareToken) {
  return apiClient.post(`/api/onboarding/films/more?share_token=${encodeURIComponent(shareToken)}`, {}, {
    headers: { "X-Session-Token": access.token }
  }).then((payload) => payload.films);
}
var init_movieService = __esm({
  "src/services/movieService.js"() {
    init_apiClient();
  }
});

// src/screens/SeenItPage.jsx
var SeenItPage_exports = {};
__export(SeenItPage_exports, {
  default: () => SeenItPage_default
});
import React19, { useEffect as useEffect4, useState as useState4 } from "react";
import { jsx as jsx19, jsxs as jsxs19 } from "react/jsx-runtime";
function formatRuntime(minutes) {
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}
function SeenItPage({ access, shareToken, onSubmit, onComplete }) {
  const [films, setFilms] = useState4([]);
  const [filmIndex, setFilmIndex] = useState4(0);
  const [error, setError] = useState4(null);
  const [selected, setSelected] = useState4(null);
  const [seen, setSeen] = useState4(0);
  const [topUps, setTopUps] = useState4(0);
  useEffect4(() => {
    let active = true;
    loadOnboardingFilms(access, shareToken).then((items) => active && setFilms(items)).catch(() => active && setError("Those films could not be loaded. Please try again."));
    return () => {
      active = false;
    };
  }, [access, shareToken]);
  async function choose(reaction) {
    if (!film || selected) return;
    const isLastFilm = filmIndex === films.length - 1;
    const answered = seen + (reaction === "havent_seen" ? 0 : 1);
    setSelected(reaction);
    setSeen(answered);
    if (!isLastFilm) {
      setFilmIndex((index) => index + 1);
      setSelected(null);
    }
    try {
      await onSubmit(film.id, reaction, shareToken);
      if (!isLastFilm) return;
      if (answered < ENOUGH_TO_READ && topUps < MAX_TOP_UPS) {
        try {
          const more = await loadMoreOnboardingFilms(access, shareToken);
          if (more?.length) {
            setFilms((current) => [...current, ...more]);
            setFilmIndex((index) => index + 1);
            setSelected(null);
            setTopUps((n) => n + 1);
            return;
          }
        } catch {
        }
      }
      onComplete();
    } catch (submissionError) {
      setSelected(null);
      setError(submissionError.message);
    }
  }
  const film = films[filmIndex];
  const swipe = useSwipeDecision({
    disabled: Boolean(selected),
    onLeft: () => choose("not_for_me"),
    onRight: () => choose("loved_it")
  });
  if (error) return /* @__PURE__ */ jsx19("main", { className: "app-page", children: /* @__PURE__ */ jsx19("p", { className: "message", children: error }) });
  if (!film) return /* @__PURE__ */ jsx19("main", { className: "app-page", children: /* @__PURE__ */ jsx19("p", { className: "message", children: "Finding films you might know\u2026" }) });
  return /* @__PURE__ */ jsx19("main", { className: "app-page seen-it-page", children: /* @__PURE__ */ jsxs19("section", { className: "phone-screen seen-it-screen", children: [
    /* @__PURE__ */ jsx19(FlowProgress, { current: filmIndex + 1, total: films.length }),
    /* @__PURE__ */ jsxs19("div", { className: "seen-it-heading", children: [
      /* @__PURE__ */ jsxs19("p", { className: "screen-label", children: [
        "Your half \xB7 ",
        films.length,
        " films"
      ] }),
      /* @__PURE__ */ jsx19("h1", { children: "Seen it? Did you like it?" })
    ] }),
    /* @__PURE__ */ jsxs19("div", { className: "seen-it-content", children: [
      /* @__PURE__ */ jsxs19("article", { className: "movie-card swipe-card", ...swipe.handlers, style: { ...film.artwork_url ? { backgroundImage: `linear-gradient(0deg, rgba(23,19,16,.82), rgba(23,19,16,.08)), url(${film.artwork_url})` } : {}, ...swipe.style }, children: [
        /* @__PURE__ */ jsx19("span", { className: "swipe-cue swipe-cue-left", "aria-hidden": "true", style: { opacity: swipe.direction === "left" ? swipe.strength : 0 }, children: "\xD7 Not for me" }),
        /* @__PURE__ */ jsx19("span", { className: "swipe-cue swipe-cue-right", "aria-hidden": "true", style: { opacity: swipe.direction === "right" ? swipe.strength : 0 }, children: "\u2665 Loved it" }),
        /* @__PURE__ */ jsxs19("div", { children: [
          /* @__PURE__ */ jsx19("h2", { children: film.title }),
          /* @__PURE__ */ jsxs19("p", { children: [
            film.year || "\u2014",
            " \xB7 ",
            film.genre,
            " \xB7 ",
            film.runtime_min ? formatRuntime(film.runtime_min) : "Runtime unavailable"
          ] })
        ] })
      ] }),
      /* @__PURE__ */ jsxs19("div", { className: "movie-reactions", "aria-label": `Your reaction to ${film.title}`, children: [
        reactions.map((reaction) => /* @__PURE__ */ jsxs19("button", { className: `movie-reaction ${reaction.id === "loved_it" ? "loved" : ""} ${reaction.id === "neutral" ? "neutral" : ""} ${selected === reaction.id ? "selected" : ""}`, type: "button", onClick: () => choose(reaction.id), disabled: Boolean(selected) || swipe.committed, children: [
          /* @__PURE__ */ jsx19("strong", { "aria-hidden": "true", children: reaction.icon }),
          /* @__PURE__ */ jsx19("span", { children: selected === reaction.id ? "Saving\u2026" : reaction.label })
        ] }, reaction.id)),
        /* @__PURE__ */ jsxs19("button", { className: `movie-reaction unseen ${selected === SKIP.id ? "selected" : ""}`, type: "button", onClick: () => choose(SKIP.id), disabled: Boolean(selected) || swipe.committed, children: [
          /* @__PURE__ */ jsx19("strong", { "aria-hidden": "true", children: SKIP.icon }),
          /* @__PURE__ */ jsx19("span", { children: selected === SKIP.id ? "Saving\u2026" : SKIP.label })
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsxs19("aside", { className: "seen-it-note", children: [
      /* @__PURE__ */ jsx19("span", { "aria-hidden": "true", children: "\u24D8" }),
      /* @__PURE__ */ jsx19("p", { children: topUps > 0 ? "A few more \u2014 we need a handful you have actually seen before we can read you. Your friend never sees these." : "Swipe right if you liked it \xB7 left if it wasn\u2019t for you. Your friend never sees these." })
    ] })
  ] }) });
}
var reactions, SKIP, ENOUGH_TO_READ, MAX_TOP_UPS, SeenItPage_default;
var init_SeenItPage = __esm({
  "src/screens/SeenItPage.jsx"() {
    init_FlowProgress();
    init_useSwipeDecision();
    init_movieService();
    reactions = [
      { id: "not_for_me", label: "Not for me", icon: "\xD7" },
      { id: "neutral", label: "It was fine", icon: "\u2248" },
      { id: "loved_it", label: "Loved it", icon: "\u2665" }
    ];
    SKIP = { id: "havent_seen", label: "Haven't seen it", icon: "\u2212" };
    ENOUGH_TO_READ = 6;
    MAX_TOP_UPS = 2;
    SeenItPage_default = SeenItPage;
  }
});

// src/screens/SessionLobbyPage.jsx
var SessionLobbyPage_exports = {};
__export(SessionLobbyPage_exports, {
  default: () => SessionLobbyPage_default
});
import React20, { useEffect as useEffect5, useMemo, useState as useState5 } from "react";
import { Fragment as Fragment11, jsx as jsx20, jsxs as jsxs20 } from "react/jsx-runtime";
function SessionLobbyPage({ access, groupSession, onStart }) {
  const [copied, setCopied] = useState5(false);
  const joinUrl = useMemo(() => `${window.location.origin}${window.location.pathname}#/join/${groupSession.share_token}`, [groupSession.share_token]);
  const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${encodeURIComponent(joinUrl)}`;
  const isHost = groupSession.host_user_id === access.user.id;
  const host = groupSession.members?.find((member) => member.user.id === groupSession.host_user_id);
  const guestCount = Math.max(0, (groupSession.members?.length || 1) - 1);
  useEffect5(() => {
    setCopied(false);
  }, [joinUrl]);
  async function copyLink() {
    await navigator.clipboard.writeText(joinUrl);
    setCopied(true);
  }
  return /* @__PURE__ */ jsx20("main", { className: "app-page", children: /* @__PURE__ */ jsxs20("section", { className: "phone-screen session-screen", "aria-label": "Invite a friend", children: [
    /* @__PURE__ */ jsxs20("div", { className: "brand", children: [
      /* @__PURE__ */ jsx20("span", { className: "brand-mark", "aria-hidden": "true", children: "\u2295" }),
      /* @__PURE__ */ jsx20("span", { children: "Something Good To Watch" })
    ] }),
    /* @__PURE__ */ jsxs20("div", { className: "session-content", children: [
      /* @__PURE__ */ jsx20("p", { className: "screen-label", children: isHost ? "Step one of two" : "You\u2019re in" }),
      isHost ? /* @__PURE__ */ jsxs20(Fragment11, { children: [
        /* @__PURE__ */ jsxs20("h1", { children: [
          "Now get",
          /* @__PURE__ */ jsx20("br", {}),
          /* @__PURE__ */ jsx20("em", { children: "a friend." })
        ] }),
        /* @__PURE__ */ jsx20("p", { className: "screen-copy", children: "This only works with two of you. Hand them your phone to scan the code, or send them the link \u2014 you will each answer on your own, without seeing what the other said." }),
        /* @__PURE__ */ jsx20("img", { className: "session-qr", src: qrUrl, alt: "QR code a friend can scan to join you" }),
        /* @__PURE__ */ jsx20("button", { className: "link-button", type: "button", onClick: copyLink, children: copied ? "Link copied" : "Copy the link for them" }),
        /* @__PURE__ */ jsxs20("div", { className: "lobby-members", "aria-live": "polite", children: [
          /* @__PURE__ */ jsx20("strong", { children: guestCount ? "They\u2019re in" : "Waiting for them to join\u2026" }),
          groupSession.members?.map((member) => /* @__PURE__ */ jsx20("span", { children: member.user.id === access.user.id ? "You" : "Your friend" }, member.user.id))
        ] })
      ] }) : /* @__PURE__ */ jsxs20(Fragment11, { children: [
        /* @__PURE__ */ jsxs20("h1", { children: [
          "You\u2019re in",
          /* @__PURE__ */ jsx20("br", {}),
          /* @__PURE__ */ jsx20("em", { children: "with them." })
        ] }),
        /* @__PURE__ */ jsx20("p", { className: "screen-copy", children: "You\u2019ll each answer separately, then we find the films you both want to watch. They start you off." })
      ] })
    ] }),
    isHost ? guestCount ? /* @__PURE__ */ jsx20("p", { className: "login-footer", children: "They\u2019re here \u2014 starting you both off\u2026" }) : /* @__PURE__ */ jsx20("button", { className: "link-button", type: "button", onClick: onStart, children: "Start without them" }) : /* @__PURE__ */ jsx20("p", { className: "login-footer", children: "Waiting for them to start you both off." })
  ] }) });
}
var SessionLobbyPage_default;
var init_SessionLobbyPage = __esm({
  "src/screens/SessionLobbyPage.jsx"() {
    SessionLobbyPage_default = SessionLobbyPage;
  }
});

// src/screens/SessionWaitingPage.jsx
var SessionWaitingPage_exports = {};
__export(SessionWaitingPage_exports, {
  default: () => SessionWaitingPage_default
});
import React21, { useState as useState6 } from "react";
import { Fragment as Fragment12, jsx as jsx21, jsxs as jsxs21 } from "react/jsx-runtime";
function SessionWaitingPage({ status, isHost, canEditAnswer, onBack, onContinue }) {
  const [error, setError] = useState6(null);
  const isYou = (member) => member.user.id === status.host_user_id === isHost;
  const complete = status.members.filter((member) => member.completed_at);
  const pending = status.members.filter((member) => !member.completed_at && !isYou(member));
  async function handleContinue() {
    setError(null);
    try {
      await onContinue();
    } catch (requestError) {
      setError(requestError.message);
    }
  }
  async function handleBack() {
    setError(null);
    try {
      await onBack();
    } catch (requestError) {
      setError(requestError.message);
    }
  }
  return /* @__PURE__ */ jsx21("main", { className: "app-page waiting-page", children: /* @__PURE__ */ jsxs21("section", { className: "phone-screen session-screen waiting-screen", "aria-label": "Waiting for your friend", children: [
    /* @__PURE__ */ jsxs21("div", { className: "brand", children: [
      /* @__PURE__ */ jsx21("span", { className: "brand-mark", "aria-hidden": "true", children: "\u2295" }),
      /* @__PURE__ */ jsx21("span", { children: "Something Good To Watch" })
    ] }),
    /* @__PURE__ */ jsxs21("div", { className: "session-content", children: [
      /* @__PURE__ */ jsx21("p", { className: "screen-label", children: "Almost there" }),
      /* @__PURE__ */ jsx21("h1", { children: pending.length ? /* @__PURE__ */ jsxs21(Fragment12, { children: [
        "Waiting for",
        /* @__PURE__ */ jsx21("br", {}),
        /* @__PURE__ */ jsx21("em", { children: "your friend." })
      ] }) : /* @__PURE__ */ jsxs21(Fragment12, { children: [
        "You\u2019re both",
        /* @__PURE__ */ jsx21("br", {}),
        /* @__PURE__ */ jsx21("em", { children: "done." })
      ] }) }),
      /* @__PURE__ */ jsx21("p", { className: "screen-copy", children: pending.length ? "They are still answering. Nothing is shared until you have both finished." : "Neither of you saw the other\u2019s answers. Here is what you have in common." }),
      /* @__PURE__ */ jsx21("div", { className: "member-list", children: status.members.map((member) => /* @__PURE__ */ jsxs21("div", { children: [
        /* @__PURE__ */ jsx21("span", { children: member.completed_at ? "\u2713" : "\u25CB" }),
        isYou(member) ? "You" : "Your friend",
        /* @__PURE__ */ jsx21("small", { children: member.completed_at ? "Ready" : "Still answering" })
      ] }, member.user.id)) }),
      error && /* @__PURE__ */ jsx21("p", { className: "message", role: "alert", children: error })
    ] }),
    isHost && pending.length > 0 && status.can_continue_without_members && /* @__PURE__ */ jsxs21("button", { className: "peach-button", type: "button", onClick: handleContinue, children: [
      "Carry on without them ",
      /* @__PURE__ */ jsx21("span", { "aria-hidden": "true", children: "\u2192" })
    ] }),
    pending.length === 0 && /* @__PURE__ */ jsx21("p", { className: "login-footer", children: "Reading you both\u2026" }),
    isHost && pending.length > 0 && !status.can_continue_without_members && /* @__PURE__ */ jsx21("p", { className: "login-footer", children: "If they get stuck, you can carry on without them after 10 minutes." })
  ] }) });
}
var SessionWaitingPage_default;
var init_SessionWaitingPage = __esm({
  "src/screens/SessionWaitingPage.jsx"() {
    SessionWaitingPage_default = SessionWaitingPage;
  }
});

// src/screens/ShortlistPage.jsx
var ShortlistPage_exports = {};
__export(ShortlistPage_exports, {
  default: () => ShortlistPage
});
import React22, { useCallback, useEffect as useEffect6, useRef as useRef2, useState as useState7 } from "react";
import { jsx as jsx22, jsxs as jsxs22 } from "react/jsx-runtime";
function ShortlistPage({ access, shareToken, matchesSeen = 0, solo = false, onDone }) {
  const [queue, setQueue] = useState7([]);
  const [state, setState] = useState7("loading");
  const [error, setError] = useState7(null);
  const [matches, setMatches] = useState7(matchesSeen);
  const voted = useRef2(/* @__PURE__ */ new Set());
  const fetching = useRef2(false);
  const finish = useCallback((films) => {
    if (films.length > matchesSeen) onDone(films);
  }, [matchesSeen, onDone]);
  const refill = useCallback(async () => {
    if (fetching.current) return;
    fetching.current = true;
    try {
      const result = await loadNextShortlistFilm(access, shareToken, matchesSeen);
      if (result.state === "shortlist") {
        finish(result.films);
        return;
      }
      if (result.state === "exhausted") {
        setState("exhausted");
        return;
      }
      setQueue((current) => {
        const have = new Set(current.map((film2) => film2.id));
        const fresh = (result.queue || [result.film]).filter((film2) => !have.has(film2.id) && !voted.current.has(film2.id));
        return [...current, ...fresh];
      });
      setState("ready");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      fetching.current = false;
    }
  }, [access, shareToken, finish, matchesSeen]);
  useEffect6(() => {
    refill();
  }, [refill]);
  useEffect6(() => {
    const poll = window.setInterval(() => {
      loadShortlistSelection(access, shareToken).then((selection) => {
        if (selection.state === "shortlist") {
          setMatches(selection.films.length);
          finish(selection.films);
        } else if (typeof selection.matches === "number") setMatches(selection.matches);
      }).catch(() => {
      });
    }, 3e3);
    return () => window.clearInterval(poll);
  }, [access, shareToken, finish]);
  const film = queue[0];
  function vote(reaction) {
    if (!film) return;
    const decided = film;
    voted.current.add(decided.id);
    setQueue((current) => current.slice(1));
    saveShortlistReaction(access, shareToken, decided.id, reaction).then((result) => {
      if (result?.state === "shortlist") finish(result.films);
      else if (typeof result?.matches === "number") setMatches(result.matches);
    }).catch((voteError) => setError(voteError.message));
  }
  const swipe = useSwipeDecision({ disabled: !film, onLeft: () => vote("no"), onRight: () => vote("yes") });
  useEffect6(() => {
    if (state === "ready" && queue.length <= REFILL_AT) refill();
  }, [state, queue.length, refill]);
  if (error && !film) return /* @__PURE__ */ jsx22("main", { className: "app-page", children: /* @__PURE__ */ jsx22("p", { className: "message", children: error }) });
  if (state === "exhausted" && !film) {
    return /* @__PURE__ */ jsx22("main", { className: "app-page", children: /* @__PURE__ */ jsx22("p", { className: "message", children: solo ? "You have been through every film we can offer you." : "You have been through every film we can offer you both." }) });
  }
  if (!film) return /* @__PURE__ */ jsx22("main", { className: "app-page", children: /* @__PURE__ */ jsx22("p", { className: "message", children: solo ? "Finding films for you\u2026" : "Finding films for the two of you\u2026" }) });
  const WANTED = 3;
  const progress = matches === 0 ? solo ? "Say yes to shortlist it" : "Both say yes to shortlist it" : matches < WANTED ? `${matches} shortlisted \xB7 ${WANTED - matches} to go` : `${matches} shortlisted \xB7 looking for more`;
  return /* @__PURE__ */ jsx22("main", { className: "app-page", children: /* @__PURE__ */ jsxs22("section", { className: "phone-screen deck-screen", children: [
    /* @__PURE__ */ jsxs22("header", { className: "deck-header", children: [
      /* @__PURE__ */ jsx22("span", { children: solo ? "Picked for you" : "Films for the two of you" }),
      /* @__PURE__ */ jsx22("span", { children: progress })
    ] }),
    /* @__PURE__ */ jsxs22("article", { className: "deck-card swipe-card", ...swipe.handlers, style: swipe.style, children: [
      /* @__PURE__ */ jsx22("span", { className: "swipe-cue swipe-cue-left", "aria-hidden": "true", style: { opacity: swipe.direction === "left" ? swipe.strength : 0 }, children: "\xD7 No" }),
      /* @__PURE__ */ jsx22("span", { className: "swipe-cue swipe-cue-right", "aria-hidden": "true", style: { opacity: swipe.direction === "right" ? swipe.strength : 0 }, children: "\u2665 Yes" }),
      /* @__PURE__ */ jsx22("div", { className: "deck-art", style: film.artwork_url ? { backgroundImage: `linear-gradient(0deg, rgba(23,19,16,.8), transparent), url(${film.artwork_url})` } : {}, children: /* @__PURE__ */ jsx22("h2", { children: film.title }) }),
      /* @__PURE__ */ jsxs22("div", { className: "deck-copy", children: [
        /* @__PURE__ */ jsx22("span", { children: film.year }),
        film.description && /* @__PURE__ */ jsx22("p", { children: film.description }),
        /* @__PURE__ */ jsx22(FilmAxisStrip, { filmId: film.id }),
        /* @__PURE__ */ jsx22("small", { children: film.note || (solo ? "Picked for you" : "Picked for both of you") })
      ] })
    ] }, film.id),
    /* @__PURE__ */ jsxs22("div", { className: "deck-actions", children: [
      /* @__PURE__ */ jsxs22("button", { type: "button", disabled: swipe.committed, onClick: () => vote("no"), children: [
        "\xD7",
        /* @__PURE__ */ jsx22("span", { children: "No" })
      ] }),
      /* @__PURE__ */ jsxs22("button", { className: "deck-heart", type: "button", disabled: swipe.committed, onClick: () => vote("yes"), children: [
        "\u2665",
        /* @__PURE__ */ jsx22("span", { children: "Yes" })
      ] })
    ] }),
    /* @__PURE__ */ jsxs22("p", { className: "deck-note", children: [
      "Swipe right for yes \xB7 left for no. ",
      solo ? "Three yeses and you have your shortlist." : "When you both say yes, it joins your shortlist."
    ] })
  ] }) });
}
var REFILL_AT;
var init_ShortlistPage = __esm({
  "src/screens/ShortlistPage.jsx"() {
    init_useSwipeDecision();
    init_FilmAxisStrip();
    init_shortlistService();
    REFILL_AT = 2;
  }
});

// src/components/atlas/TasteDimensions.jsx
import React23 from "react";
import { Fragment as Fragment13, jsx as jsx23, jsxs as jsxs23 } from "react/jsx-runtime";
function pct2(x) {
  return `${(x * 100).toFixed(1)}%`;
}
function Fig({ from, name, suffix = "" }) {
  const f = from?.[name];
  if (!f) return /* @__PURE__ */ jsx23("b", { children: "\u2014" });
  return /* @__PURE__ */ jsxs23("b", { title: [f.note, f.source].filter(Boolean).join(" \xB7 "), children: [
    f.display ?? f.value,
    suffix
  ] });
}
function TasteDimensions({ taste }) {
  const dims = taste?.dimensions || [];
  const found = taste?.findings;
  if (!dims.length) return null;
  const named = dims.filter((d) => d.status === "named");
  const unnamed = dims.filter((d) => d.status === "unnamed");
  const franchise = dims.filter((d) => d.status === "franchise");
  return /* @__PURE__ */ jsxs23("section", { className: "taste", "aria-labelledby": "taste", children: [
    /* @__PURE__ */ jsx23("h2", { id: "taste", children: "What people actually choose by" }),
    /* @__PURE__ */ jsxs23("p", { children: [
      "The axes below are what films ",
      /* @__PURE__ */ jsx23("em", { children: "argue" }),
      ". They are not what people choose by. Shown a film someone rated highly and one they rated poorly, across",
      " ",
      /* @__PURE__ */ jsx23(Fig, { from: found, name: "ml_raters" }),
      " outside raters:"
    ] }),
    /* @__PURE__ */ jsxs23("table", { className: "figures", children: [
      /* @__PURE__ */ jsx23("thead", { children: /* @__PURE__ */ jsxs23("tr", { children: [
        /* @__PURE__ */ jsx23("th", { children: "Ranked by" }),
        /* @__PURE__ */ jsx23("th", { children: "One person" }),
        /* @__PURE__ */ jsx23("th", { children: "Two people" })
      ] }) }),
      /* @__PURE__ */ jsxs23("tbody", { children: [
        /* @__PURE__ */ jsxs23("tr", { children: [
          /* @__PURE__ */ jsx23("td", { children: "The moral axes" }),
          /* @__PURE__ */ jsx23("td", { className: "n", children: /* @__PURE__ */ jsx23(Fig, { from: found, name: "pairwise_moral_one" }) }),
          /* @__PURE__ */ jsx23("td", { className: "n", children: /* @__PURE__ */ jsx23(Fig, { from: found, name: "pairwise_moral_two" }) })
        ] }),
        /* @__PURE__ */ jsxs23("tr", { children: [
          /* @__PURE__ */ jsx23("td", { children: "Ideological list membership" }),
          /* @__PURE__ */ jsx23("td", { className: "n", children: /* @__PURE__ */ jsx23(Fig, { from: found, name: "pairwise_sets_one" }) }),
          /* @__PURE__ */ jsx23("td", { className: "n", children: /* @__PURE__ */ jsx23(Fig, { from: found, name: "pairwise_sets_two" }) })
        ] }),
        /* @__PURE__ */ jsxs23("tr", { className: "lead", children: [
          /* @__PURE__ */ jsx23("td", { children: "Which films are liked by the same people" }),
          /* @__PURE__ */ jsx23("td", { className: "n", children: /* @__PURE__ */ jsx23(Fig, { from: found, name: "pairwise_cf_one" }) }),
          /* @__PURE__ */ jsx23("td", { className: "n", children: /* @__PURE__ */ jsx23(Fig, { from: found, name: "pairwise_cf_two" }) })
        ] }),
        /* @__PURE__ */ jsxs23("tr", { children: [
          /* @__PURE__ */ jsx23("td", { children: /* @__PURE__ */ jsx23("em", { children: "chance" }) }),
          /* @__PURE__ */ jsx23("td", { className: "n", children: /* @__PURE__ */ jsx23(Fig, { from: found, name: "pairwise_chance" }) }),
          /* @__PURE__ */ jsx23("td", { className: "n", children: /* @__PURE__ */ jsx23(Fig, { from: found, name: "pairwise_chance" }) })
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsxs23("p", { children: [
      "So the dimensions of taste were found the same way the moral ones were \u2014 nobody chose them, only what came back from independent halves of the raters was kept (",
      /* @__PURE__ */ jsx23(Fig, { from: found, name: "replication_floor" }),
      " and above), and names came last, from",
      " ",
      /* @__PURE__ */ jsx23(Fig, { from: found, name: "tag_vocab" }),
      " human-assigned tags rather than from film titles. A model shown titles alone produced fourteen confident genre labels; thirteen survived no external check."
    ] }),
    /* @__PURE__ */ jsxs23("table", { className: "figures taste-table", children: [
      /* @__PURE__ */ jsx23("thead", { children: /* @__PURE__ */ jsxs23("tr", { children: [
        /* @__PURE__ */ jsx23("th", { children: "Dimension of taste" }),
        /* @__PURE__ */ jsx23("th", { children: "Variation" }),
        /* @__PURE__ */ jsx23("th", { children: "Replicates" }),
        /* @__PURE__ */ jsx23("th", { children: "Evidence" })
      ] }) }),
      /* @__PURE__ */ jsx23("tbody", { children: named.map((d, i) => /* @__PURE__ */ jsxs23("tr", { className: i === 0 ? "lead" : void 0, children: [
        /* @__PURE__ */ jsxs23("td", { children: [
          d.pole_high,
          " ",
          /* @__PURE__ */ jsx23("i", { "aria-hidden": "true", children: "\u2194" }),
          " ",
          d.pole_low,
          /* @__PURE__ */ jsx23("small", { className: "taste-tags", children: d.tags_high.slice(0, 3).join(", ") })
        ] }),
        /* @__PURE__ */ jsx23("td", { className: "n", children: pct2(d.variance) }),
        /* @__PURE__ */ jsx23("td", { className: "n", children: d.replication.toFixed(2) }),
        /* @__PURE__ */ jsx23("td", { className: "n", children: d.evidence.toFixed(2) })
      ] }, d.dim_id)) })
    ] }),
    /* @__PURE__ */ jsxs23("p", { className: "taste-lead-note", children: [
      "The largest fact about film taste is how good the film is held to be \u2014",
      " ",
      /* @__PURE__ */ jsx23(Fig, { from: found, name: "quality_vs_imdb" }),
      " against IMDb rating and",
      " ",
      /* @__PURE__ */ jsx23(Fig, { from: found, name: "quality_vs_tag" }),
      " against the tag ",
      /* @__PURE__ */ jsx23("em", { children: "surprisingly clever" }),
      ", from data the namer never saw. None of the fourteen is moral."
    ] }),
    (unnamed.length > 0 || franchise.length > 0) && /* @__PURE__ */ jsxs23("p", { className: "atlas-note", children: [
      unnamed.length > 0 && /* @__PURE__ */ jsxs23(Fragment13, { children: [
        /* @__PURE__ */ jsxs23("b", { children: [
          unnamed.length,
          " replicate and cannot be named."
        ] }),
        " No instrument tried \u2014 genre, ratings, era, ",
        " ",
        /* @__PURE__ */ jsx23(Fig, { from: found, name: "tag_vocab" }),
        " tags \u2014 characterises them. Published unnamed rather than labelled.",
        " "
      ] }),
      franchise.length > 0 && /* @__PURE__ */ jsxs23(Fragment13, { children: [
        /* @__PURE__ */ jsxs23("b", { children: [
          franchise.length,
          " are franchise artefacts."
        ] }),
        " A dimension whose defining tags are",
        " ",
        /* @__PURE__ */ jsx23("em", { children: "new zealand" }),
        " and ",
        /* @__PURE__ */ jsx23("em", { children: "tolkien" }),
        " is one film series, not a dimension of taste."
      ] })
    ] }),
    /* @__PURE__ */ jsx23("h3", { children: "What that does to the moral axes \u2014 and what it does not" }),
    /* @__PURE__ */ jsxs23("p", { children: [
      "Taste accounts for ",
      /* @__PURE__ */ jsx23(Fig, { from: found, name: "taste_explains_axis1", suffix: "%" }),
      " of the leading moral axis and almost none of the second. Morality accounts for essentially none of any taste dimension. The two spaces share",
      " ",
      /* @__PURE__ */ jsx23(Fig, { from: found, name: "shared_variance", suffix: "%" }),
      " of their variance \u2014",
      " ",
      /* @__PURE__ */ jsx23(Fig, { from: found, name: "cca" }),
      " against ",
      /* @__PURE__ */ jsx23(Fig, { from: found, name: "cca_null" }),
      " on permuted films \u2014 leaving three quarters of the moral signal invisible to preference."
    ] }),
    /* @__PURE__ */ jsx23("p", { children: "Which raises the suspicion that the axes were only ever taste. So every proposition's verdicts were replaced with what remains after its taste position is subtracted, and the discovery was run again from those residuals, free to come out differently. The propositions did regroup. The axes reassembled anyway." }),
    /* @__PURE__ */ jsxs23("table", { className: "figures", children: [
      /* @__PURE__ */ jsx23("thead", { children: /* @__PURE__ */ jsxs23("tr", { children: [
        /* @__PURE__ */ jsx23("th", { children: "Rebuilt without taste, against the original" }),
        /* @__PURE__ */ jsx23("th", { children: "Deterministic pessimism" }),
        /* @__PURE__ */ jsx23("th", { children: "Divine order" })
      ] }) }),
      /* @__PURE__ */ jsxs23("tbody", { children: [
        /* @__PURE__ */ jsxs23("tr", { className: "lead", children: [
          /* @__PURE__ */ jsxs23("td", { children: [
            "Redemptive hope ",
            /* @__PURE__ */ jsx23("i", { "aria-hidden": "true", children: "\u2194" }),
            " Deterministic retribution"
          ] }),
          /* @__PURE__ */ jsx23("td", { className: "n", children: /* @__PURE__ */ jsx23(Fig, { from: found, name: "rebuild_axis1" }) }),
          /* @__PURE__ */ jsx23("td", { className: "n", children: "0.11" })
        ] }),
        /* @__PURE__ */ jsxs23("tr", { className: "lead", children: [
          /* @__PURE__ */ jsxs23("td", { children: [
            "Inherited order ",
            /* @__PURE__ */ jsx23("i", { "aria-hidden": "true", children: "\u2194" }),
            " Self-determination"
          ] }),
          /* @__PURE__ */ jsx23("td", { className: "n", children: "0.15" }),
          /* @__PURE__ */ jsx23("td", { className: "n", children: /* @__PURE__ */ jsx23(Fig, { from: found, name: "rebuild_axis2" }) })
        ] }),
        /* @__PURE__ */ jsxs23("tr", { children: [
          /* @__PURE__ */ jsx23("td", { children: /* @__PURE__ */ jsx23("em", { children: "shuffled films" }) }),
          /* @__PURE__ */ jsx23("td", { className: "n", children: /* @__PURE__ */ jsx23(Fig, { from: found, name: "rebuild_null" }) }),
          /* @__PURE__ */ jsx23("td", { className: "n", children: /* @__PURE__ */ jsx23(Fig, { from: found, name: "rebuild_null" }) })
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsxs23("p", { children: [
      "The names came back independently and so did the placements \u2014 which is the distinction that matters. This project has already believed two readings had replicated because their",
      /* @__PURE__ */ jsx23("em", { children: " names" }),
      " matched, when their positions agreed no better than",
      " ",
      /* @__PURE__ */ jsx23(Fig, { from: found, name: "names_matched_positions_did_not" }),
      "."
    ] }),
    /* @__PURE__ */ jsxs23("p", { className: "taste-conclusion", children: [
      /* @__PURE__ */ jsx23("em", { children: "Morality cannot rank films because it is orthogonal to taste, and is worth measuring for the same reason." }),
      " The part invisible to preference data still separates lists built by Catholics from lists built by Satanists."
    ] })
  ] });
}
var init_TasteDimensions = __esm({
  "src/components/atlas/TasteDimensions.jsx"() {
  }
});

// src/screens/TastePage.jsx
var TastePage_exports = {};
__export(TastePage_exports, {
  default: () => TastePage
});
import React24 from "react";
import { Fragment as Fragment14, jsx as jsx24, jsxs as jsxs24 } from "react/jsx-runtime";
function pct3(x) {
  return `${(x * 100).toFixed(1)}%`;
}
function poles(films, dimId, take = 4) {
  const rows = films.map((f) => ({ title: f.title, at: f.position?.[String(dimId)] })).filter((f) => typeof f.at === "number").sort((a, b) => b.at - a.at);
  return { high: rows.slice(0, take), low: rows.slice(-take).reverse() };
}
function TastePage({ onBack, onAtlas }) {
  const [taste, setTaste] = React24.useState(null);
  const [error, setError] = React24.useState(null);
  React24.useEffect(() => {
    let live = true;
    loadTaste().then((t) => live && setTaste(t)).catch(() => live && setError("The taste dimensions could not be loaded."));
    return () => {
      live = false;
    };
  }, []);
  const dims = taste?.dimensions || [];
  const byReadability = [...dims].sort(
    (a, b) => (b.profile_reliability ?? 0) - (a.profile_reliability ?? 0)
  );
  const named = byReadability.filter((d) => d.status === "named");
  return /* @__PURE__ */ jsx24("main", { className: "atlas-page", children: /* @__PURE__ */ jsxs24("div", { className: "atlas-wrap", children: [
    /* @__PURE__ */ jsxs24("header", { className: "atlas-header", children: [
      onBack && /* @__PURE__ */ jsx24("button", { type: "button", className: "back-button", onClick: onBack, children: "\u2190" }),
      /* @__PURE__ */ jsxs24("div", { children: [
        /* @__PURE__ */ jsx24("h1", { children: "What kind of film do people choose?" }),
        /* @__PURE__ */ jsx24("p", { className: "atlas-note", children: "A second set of dimensions, found the same way as the moral ones but from a different question: not what a film argues, but which films the same people enjoy. Derived from 162,000 outside raters who never saw any of this." }),
        /* @__PURE__ */ jsxs24("p", { className: "atlas-note", children: [
          "It is here as the comparison the moral axes have to survive \u2014 and they do not survive it in the way you would expect.",
          " ",
          onAtlas && /* @__PURE__ */ jsx24("button", { type: "button", className: "link-button", onClick: onAtlas, children: "The moral axes are on the atlas \u2192" })
        ] })
      ] })
    ] }),
    error && /* @__PURE__ */ jsx24("section", { children: /* @__PURE__ */ jsx24("p", { className: "atlas-note", children: error }) }),
    !taste && !error && /* @__PURE__ */ jsx24("section", { children: /* @__PURE__ */ jsx24("p", { className: "message", children: "Reading the dimensions\u2026" }) }),
    taste && /* @__PURE__ */ jsxs24(Fragment14, { children: [
      /* @__PURE__ */ jsx24(TasteDimensions, { taste }),
      /* @__PURE__ */ jsxs24("section", { className: "taste", children: [
        /* @__PURE__ */ jsx24("h2", { children: "Every dimension, and which of them a profile can use" }),
        /* @__PURE__ */ jsx24("p", { children: "Sixteen dimensions replicate across independent halves of the raters. Six can be named. That is not the same question as which are worth showing somebody about themselves \u2014 a dimension can be large in the corpus and still fail to place a person who has rated a dozen films, because people barely differ on it." }),
        /* @__PURE__ */ jsxs24("p", { children: [
          /* @__PURE__ */ jsx24("b", { children: "Places a person" }),
          " is measured directly: split a rater's films in two, place them from each half, and correlate the two placements across raters. The top",
          " ",
          SHOWN_IN_PROFILE,
          " are what a profile shows, and they are not the largest",
          " ",
          SHOWN_IN_PROFILE,
          "."
        ] }),
        /* @__PURE__ */ jsx24("div", { className: "scroll", children: /* @__PURE__ */ jsxs24("table", { className: "figures taste-table", children: [
          /* @__PURE__ */ jsx24("thead", { children: /* @__PURE__ */ jsxs24("tr", { children: [
            /* @__PURE__ */ jsx24("th", { children: "Dimension" }),
            /* @__PURE__ */ jsx24("th", { children: "Places a person" }),
            /* @__PURE__ */ jsx24("th", { children: "Variation" }),
            /* @__PURE__ */ jsx24("th", { children: "Replicates" }),
            /* @__PURE__ */ jsx24("th", { children: "Status" })
          ] }) }),
          /* @__PURE__ */ jsx24("tbody", { children: byReadability.map((d, i) => /* @__PURE__ */ jsxs24("tr", { className: i < SHOWN_IN_PROFILE ? "lead" : void 0, children: [
            /* @__PURE__ */ jsxs24("td", { children: [
              d.status === "unnamed" ? /* @__PURE__ */ jsx24("em", { children: "unnamed" }) : /* @__PURE__ */ jsxs24(Fragment14, { children: [
                d.pole_low,
                " ",
                /* @__PURE__ */ jsx24("i", { "aria-hidden": "true", children: "\u2194" }),
                " ",
                d.pole_high
              ] }),
              i < SHOWN_IN_PROFILE && /* @__PURE__ */ jsx24("small", { className: "taste-tags", children: "shown in profiles" })
            ] }),
            /* @__PURE__ */ jsx24("td", { className: "n", children: typeof d.profile_reliability === "number" ? d.profile_reliability.toFixed(2) : "\u2014" }),
            /* @__PURE__ */ jsx24("td", { className: "n", children: pct3(d.variance) }),
            /* @__PURE__ */ jsx24("td", { className: "n", children: d.replication.toFixed(2) }),
            /* @__PURE__ */ jsx24("td", { className: "n", children: d.status })
          ] }, d.dim_id)) })
        ] }) }),
        /* @__PURE__ */ jsx24("p", { className: "atlas-note", children: "The break falls after the fifth: those place a person between 0.41 and 0.51, and the sixth drops to 0.25. A row for that one would be a confident reading of noise, which is the only kind of row worth cutting." })
      ] }),
      /* @__PURE__ */ jsxs24("section", { className: "taste", children: [
        /* @__PURE__ */ jsx24("h2", { children: "The films at each end" }),
        /* @__PURE__ */ jsx24("p", { children: "Nothing above can be checked by eye. This can: for each named dimension, the films the data puts furthest along it, in both directions. The names were written from 1,128 human-assigned tags and never from titles \u2014 so if the titles look right, that is a check the naming could have failed." }),
        named.map((d) => {
          const { high, low } = poles(taste.films || [], d.dim_id);
          return /* @__PURE__ */ jsxs24("div", { className: "taste-poles", children: [
            /* @__PURE__ */ jsxs24("h3", { children: [
              d.pole_low,
              " ",
              /* @__PURE__ */ jsx24("i", { "aria-hidden": "true", children: "\u2194" }),
              " ",
              d.pole_high
            ] }),
            /* @__PURE__ */ jsxs24("div", { className: "taste-poles-row", children: [
              /* @__PURE__ */ jsxs24("div", { children: [
                /* @__PURE__ */ jsx24("span", { className: "taste-pole-label", children: d.pole_low }),
                /* @__PURE__ */ jsx24("ul", { children: low.map((f) => /* @__PURE__ */ jsx24("li", { children: f.title }, f.title)) })
              ] }),
              /* @__PURE__ */ jsxs24("div", { children: [
                /* @__PURE__ */ jsx24("span", { className: "taste-pole-label", children: d.pole_high }),
                /* @__PURE__ */ jsx24("ul", { children: high.map((f) => /* @__PURE__ */ jsx24("li", { children: f.title }, f.title)) })
              ] })
            ] })
          ] }, d.dim_id);
        })
      ] })
    ] })
  ] }) });
}
var SHOWN_IN_PROFILE;
var init_TastePage = __esm({
  "src/screens/TastePage.jsx"() {
    init_TasteDimensions();
    init_factorService();
    SHOWN_IN_PROFILE = 5;
  }
});

// src/screens/TestCompletePage.jsx
var TestCompletePage_exports = {};
__export(TestCompletePage_exports, {
  default: () => TestCompletePage_default
});
import React25 from "react";
import { jsx as jsx25 } from "react/jsx-runtime";
function TestCompletePage({ access, shareToken, onContinue }) {
  return /* @__PURE__ */ jsx25(CompassScreen_default, { access, shareToken, onContinue });
}
var TestCompletePage_default;
var init_TestCompletePage = __esm({
  "src/screens/TestCompletePage.jsx"() {
    init_CompassScreen();
    TestCompletePage_default = TestCompletePage;
  }
});

// import("./src/screens/**/*") in smoke.mjs
var globImport_src_screens = __glob({
  "./src/screens/AtlasPage.jsx": () => Promise.resolve().then(() => (init_AtlasPage(), AtlasPage_exports)),
  "./src/screens/CompassScreen.jsx": () => Promise.resolve().then(() => (init_CompassScreen(), CompassScreen_exports)),
  "./src/screens/CorpusPage.jsx": () => Promise.resolve().then(() => (init_CorpusPage(), CorpusPage_exports)),
  "./src/screens/LandingPage.jsx": () => Promise.resolve().then(() => (init_LandingPage(), LandingPage_exports)),
  "./src/screens/MatchPage.jsx": () => Promise.resolve().then(() => (init_MatchPage(), MatchPage_exports)),
  "./src/screens/SeenItPage.jsx": () => Promise.resolve().then(() => (init_SeenItPage(), SeenItPage_exports)),
  "./src/screens/SessionLobbyPage.jsx": () => Promise.resolve().then(() => (init_SessionLobbyPage(), SessionLobbyPage_exports)),
  "./src/screens/SessionWaitingPage.jsx": () => Promise.resolve().then(() => (init_SessionWaitingPage(), SessionWaitingPage_exports)),
  "./src/screens/ShortlistPage.jsx": () => Promise.resolve().then(() => (init_ShortlistPage(), ShortlistPage_exports)),
  "./src/screens/TastePage.jsx": () => Promise.resolve().then(() => (init_TastePage(), TastePage_exports)),
  "./src/screens/TestCompletePage.jsx": () => Promise.resolve().then(() => (init_TestCompletePage(), TestCompletePage_exports))
});

// smoke.mjs
global.window = {
  location: { hash: "#/" },
  addEventListener() {
  },
  removeEventListener() {
  },
  matchMedia: () => ({ matches: false, addEventListener() {
  }, removeEventListener() {
  } }),
  requestAnimationFrame: (f) => f(),
  scrollTo() {
  }
};
global.document = { documentElement: { style: {} }, addEventListener() {
}, removeEventListener() {
} };
global.ResizeObserver = class {
  observe() {
  }
  disconnect() {
  }
  unobserve() {
  }
};
global.fetch = () => new Promise(() => {
});
global.localStorage = { getItem: () => null, setItem() {
}, removeItem() {
} };
var React26 = (await import("react")).default;
var { renderToStaticMarkup } = await import("react-dom/server");
var fs = await import("node:fs");
var screens = fs.readdirSync("./src/screens").filter((f) => f.endsWith(".jsx"));
var bad = 0;
for (const file of screens) {
  const mod = await globImport_src_screens(`./src/screens/${file}`);
  const Screen = mod.default;
  try {
    renderToStaticMarkup(React26.createElement(Screen, {
      onBack: () => {
      },
      onContinue: () => {
      },
      onAtlas: () => {
      },
      navigate: () => {
      },
      access: null,
      shareToken: null,
      solo: true
    }));
    console.log(`ok    ${file}`);
  } catch (e) {
    bad++;
    console.log(`FAIL  ${file}: ${e.constructor.name}: ${String(e.message).slice(0, 90)}`);
  }
}
console.log(`
${screens.length - bad} of ${screens.length} screens execute`);
process.exit(bad ? 1 : 0);
