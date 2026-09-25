import { element } from "../dom/elements.js";

/**
 * A bar + line combination chart drawn as inline SVG.
 *
 * The series/axis/legend/tooltip vocabulary follows Apache ECharts so the
 * shape is familiar, but nothing is imported: PRD section 6.1 requires charts
 * to be internal SVG or Canvas and forbids external chart libraries and CDN
 * requests, and the project ships without a bundler.
 *
 * Lifecycle: one instance owns one container. `destroy()` disconnects the
 * ResizeObserver and empties the container; the observer also self-disconnects
 * if it ever fires for a detached node, so a route change that drops the page
 * without calling destroy cannot leave an observer running.
 */

const SVG_NS = "http://www.w3.org/2000/svg";
const NARROW_WIDTH = 560;
const COMPACT_WIDTH = 400;
/** Below this the axis and category labels start colliding. */
const MIN_HEIGHT = 150;
/**
 * And above this nothing is gained, so the drawing stops growing.
 *
 * The chart measures itself from the box it is in, and that box can be sized by
 * its contents — which include this chart. Without a ceiling the two feed each
 * other: a drawing one pixel taller makes a container one pixel taller, and the
 * page ends up with a 130,000px chart and a scrollbar to nowhere. A ceiling makes
 * that loop terminate at a height a trend chart actually wants, and it costs
 * nothing: no panel on this page is taller than this.
 */
const MAX_HEIGHT = 520;

/**
 * The narrowest a column may be drawn before the plot starts scrolling instead.
 *
 * A chart that divides its width by however many points it has keeps every
 * column on screen at any cost, and the cost on a long series is columns too
 * thin to read or to hit. Past a floor the plot grows wider than its viewport
 * and scrolls, so a column stays a column however many months the project runs.
 */
const MIN_BAND = 46;
const MIN_BAND_NARROW = 38;
const MIN_BAND_COMPACT = 28;

/**
 * Vertical room given back to a horizontal scrollbar when one appears.
 *
 * Measured rather than assumed would mean drawing, reading the scrollbar's
 * height and drawing again; the bar is styled thin, and the allowance is set
 * above what that costs so the category labels never end up under it.
 */
const SCROLLBAR_ALLOWANCE = 12;

/**
 * Room at the drawing's right edge, where the newest month sits.
 *
 * It used to hold the overhanging half of a centred label, back when month zero
 * was drawn here. Tilted labels hang from their own band and reach only to the
 * left, so nothing overhangs this edge any more; what is left is breathing space
 * between the newest column and the clip.
 */
const EDGE_GUTTER = 22;

/**
 * How far the category labels lean, and why they lean at all.
 *
 * A horizontal month name is as wide as the word. «اردیبهشت» under a band sized
 * for «دی» either runs into its neighbours or has to be dropped — and dropping
 * was what made months vanish from under the columns, on exactly the chart where
 * the reader is trying to find one. Tilted, the width is spent diagonally:
 * neighbouring labels are separated by the BAND's width times this tilt rather
 * than by the word's own width, which every band on this chart clears at every
 * size it draws. So no month loses its name, and none is dropped.
 *
 * Negative is anticlockwise in SVG's own axes, which tips the text down towards
 * the far edge — reading it right to left goes downwards, the way the labels
 * were asked to run.
 */
const CATEGORY_TILT = -45;
/** Sine and cosine of 45°, which are the same number. */
const TILT = Math.SQRT1_2;
/**
 * An em-width estimate for this typeface rather than a measurement: measuring
 * every label would mean laying out text only to ask how wide it is, and erring
 * wide costs padding rather than a dropped word.
 */
const CATEGORY_EM = 0.62;
/** Between the plot's floor and where a label begins. */
const CATEGORY_GAP = 9;

function svg(tag, attributes = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, String(value)));
  return node;
}

/**
 * The lane the value axis lives in, measured rather than guessed.
 *
 * It used to be a flat 44px, which fit the amounts this project happens to have
 * and nothing larger: a project an order of magnitude up writes «۱٬۲۳۴٫۵۶»
 * there and runs it into the chart, or off the edge. `axisWidth` is the widest
 * label as the browser actually renders it, and the lane is that plus a gap on
 * each side — one to keep the numbers off the plot, one to keep them off the
 * edge — so the boundary holds whatever the numbers turn out to be.
 */
function geometry(width, height, isNarrow, isCompact, axisWidth, categoryWidth) {
  const barWidthRatio = isCompact ? 0.52 : 0.44;
  // A short box spends a punishing share of itself on padding, so trim the top
  // (which only holds air) and keep the bottom, which carries the month labels.
  const isShort = height < 200;
  // The clear space between the plot and the numbers. It is spent twice — once
  // widening the lane, once holding the first digit off the drawing's edge — so
  // it is the one number that decides how separate the two read as.
  const gap = isCompact ? 11 : 16;
  const edge = isCompact ? 4 : 7;
  // A floor so a chart of single digits does not jump about, and a ceiling so a
  // very long amount on a very narrow chart cannot squeeze the plot away.
  const lane = Math.min(
    Math.max(Math.ceil(axisWidth) + gap + edge, isCompact ? 30 : 40),
    Math.max(Math.round(width * 0.32), 40),
  );
  return {
    width,
    height,
    padding: {
      // Inline-start of an RTL chart is the right edge, where the value axis
      // sits.
      value: lane,
      top: isShort ? 8 : 16,
      // A tilted label hangs below the plot's floor by its own width times the
      // tilt, and reaches the same distance towards the far edge. Both are
      // reserved here rather than discovered by clipping. The ceiling is what
      // stops a category nobody planned for from squeezing the plot away.
      bottom: Math.min(
        Math.max(30, Math.round(CATEGORY_GAP + categoryWidth * TILT) + 4),
        Math.round(height * 0.38),
      ),
      far: Math.max(isCompact ? 10 : 16, Math.ceil(categoryWidth * TILT)),
    },
    axisGap: gap,
    axisEdge: edge,
    barWidthRatio,
    fontSize: isCompact ? 9 : isNarrow ? 10 : 11,
  };
}

export function createCombinationChart({
  categoryKey = "label",
  narrowCategoryKey = "shortLabel",
  barSeries,
  lineSeries,
  formatValue = (value) => String(value),
  /** The unrounded figure behind an axis number. Without it the axis is inert. */
  formatExactValue,
  renderTooltip,
  ariaLabel = "نمودار ترکیبی",
} = {}) {
  const container = element("div", "combo-chart");
  const surface = element("div", "combo-chart__surface");
  const tooltip = element("div", "combo-chart__tooltip");
  tooltip.setAttribute("role", "status");
  tooltip.hidden = true;
  // The axis numbers are HTML over the plot rather than text inside it. SVG text
  // cannot carry generated content, so a number drawn in the picture could never
  // have the ::after tooltip every other compacted amount in this project has —
  // and a chart with a tooltip of its own is a chart that has to be learned
  // separately. Being HTML also means the widest one can simply be asked its
  // width instead of measured through a hidden stand-in.
  const axisLayer = element("div", "combo-chart__axis");
  /**
   * The plot scrolls; the value axis does not.
   *
   * The axis numbers are positioned against the SURFACE, so a plot that scrolled
   * with them still inside it would slide its columns under the numbers. Keeping
   * the scroller a sibling of the axis layer reserves the axis its own lane at
   * the inline start, and the columns scroll past it without ever reaching it.
   *
   * `direction: ltr` on the scroller is deliberate and is not a reading order:
   * the drawing places its months along physical coordinates of its own, and an
   * RTL scroll container would make `scrollLeft` count from the opposite end of
   * them. Left-to-right keeps `scrollLeft: 0` meaning the drawing's left edge --
   * the project's FIRST month -- which is the fixed point every offset below is
   * measured from.
   */
  const scroller = element("div", "combo-chart__scroll finance-scrollbar");
  surface.append(scroller, tooltip, axisLayer);

  /** Renders the axis numbers and answers how wide the widest of them is. */
  function layoutAxis(fontSize) {
    const nodes = ticks.map((tick) => {
      const shown = formatValue(tick.valueIrr) ?? "";
      const exact = formatExactValue?.(tick.valueIrr);
      const node = element("span", `combo-chart__axis-value numeric${exact ? " compact-money" : ""}`, shown);
      node.style.fontSize = `${fontSize}px`;
      if (exact) {
        node.title = exact;
        node.setAttribute("aria-label", exact);
        node.tabIndex = 0;
      }
      return node;
    });
    axisLayer.replaceChildren(...nodes);
    // Zero while the panel holding the chart is still hidden, which is the same
    // moment every other measurement here reads zero; the reveal redraws.
    return { nodes, widest: nodes.reduce((result, node) => Math.max(result, node.offsetWidth), 0) };
  }
  container.append(surface);

  let points = [];
  let ticks = [];
  let observer = null;
  let activeIndex = -1;
  let destroyed = false;
  // Set by setData alone. A redraw caused by a resize keeps the reader where
  // they scrolled to; new data opens the chart at its focus column again.
  let pendingScrollReset = true;
  /**
   * The column the chart opens on, or -1 for its inline start.
   *
   * The newest column is not always the one to open on. A window that reaches
   * into the future ends on a month nobody has reached yet, and a chart that
   * opened there would show the reader a screen of empty months and make them
   * scroll to find out where the project actually is.
   */
  let focusIndex = -1;

  function hideTooltip() {
    activeIndex = -1;
    tooltip.hidden = true;
    tooltip.replaceChildren();
    surface.querySelectorAll(".combo-chart__hit--active").forEach((node) => node.classList.remove("combo-chart__hit--active"));
  }

  function showTooltip(index, hit) {
    if (!renderTooltip || !points[index]) return;
    activeIndex = index;
    tooltip.replaceChildren(renderTooltip(points[index]));
    tooltip.hidden = false;
    surface.querySelectorAll(".combo-chart__hit--active").forEach((node) => node.classList.remove("combo-chart__hit--active"));
    hit.classList.add("combo-chart__hit--active");

    // Keep the panel inside the surface on both edges rather than letting it
    // push the page sideways.
    const surfaceWidth = surface.clientWidth;
    // The column's centre is a coordinate inside the DRAWING, which may be
    // scrolled; the panel is positioned against the surface, which is not.
    const bandCentre = Number(hit.getAttribute("data-centre")) - scroller.scrollLeft;
    // Measured against the start of the surface, then placed: the panel's own
    // width is only known once it is somewhere definite.
    tooltip.style.left = "0px";
    const panelWidth = tooltip.offsetWidth;
    const left = Math.min(Math.max(bandCentre - panelWidth / 2, 4), Math.max(surfaceWidth - panelWidth - 4, 4));
    tooltip.style.left = `${left}px`;
  }

  function draw() {
    if (destroyed) return;
    /**
     * Whether this drawing is built on a width the container actually has.
     *
     * A panel that is still hidden measures zero and the floor below invents
     * 240px, which draws something plausible and is the right thing to do — the
     * reveal redraws against the real width. But an OPENING SCROLL OFFSET
     * computed against an invented width is not where the reader should land,
     * and a drawing that narrow has no overflow to scroll, so assigning one
     * silently clamps to zero. That was invisible while the chart opened at zero
     * anyway; it is not invisible now that the newest month is at the far end.
     */
    const measured = surface.clientWidth > 0;
    const width = Math.max(Math.floor(surface.clientWidth), 240);
    const isNarrow = width < NARROW_WIDTH;
    const isCompact = width < COMPACT_WIDTH;
    // Fill the height the container was given; the fallback only applies when
    // the container has none of its own, such as a panel that is still hidden.
    const available = Math.floor(surface.clientHeight);
    const fallback = isCompact ? 230 : isNarrow ? 260 : 300;
    // The stylesheet stretches the SVG to its container, so the drawing must fit
    // the height the container actually has: painting taller only pushes the
    // category row past the clip. The floor applies to the fallback alone, for a
    // panel that is still hidden and has no height of its own yet.
    const height = Math.min(
      available > 0 ? available : Math.max(fallback, MIN_HEIGHT),
      MAX_HEIGHT,
    );
    const fontSize = isCompact ? 9 : isNarrow ? 10 : 11;
    const axis = layoutAxis(fontSize);
    const categoryTextOf = (point) => point[isNarrow ? narrowCategoryKey : categoryKey];
    const categoryWidth = points.reduce(
      (widest, point) => Math.max(widest, String(categoryTextOf(point) ?? "").length),
      0,
    ) * fontSize * CATEGORY_EM;
    const box = geometry(width, height, isNarrow, isCompact, axis.widest, categoryWidth);

    // The axis lane is taken out of the surface before the drawing is sized, so
    // the drawing holds the plot alone and the lane cannot be scrolled over.
    const viewportWidth = Math.max(width - box.padding.value, 120);
    /**
     * And the lane is kept clear of the SCROLLER too, which is what actually
     * reserves it.
     *
     * Every figure below already subtracted it, so a drawing that fits was laid
     * out clear of the numbers and looked right. But the scroller is a plain
     * block filling the surface, so it spanned the lane as well — and the moment
     * the months outgrew the view, the columns scrolled straight under the
     * numbers. Measured on this project at 1440px: the drawing's right edge came
     * 26px past the first digit, with the newest month's bar behind it.
     *
     * A margin rather than a width, so the scroller takes whatever room is
     * actually left instead of a width computed from a floor that a very narrow
     * surface does not have.
     *
     * PHYSICAL right, deliberately, and the same for the numbers below. The lane
     * is on the right because that is this page's inline start — but a LOGICAL
     * property cannot say so here: the surface and the axis layer are RTL while
     * this scroller declares `direction: ltr` for its scroll coordinates, so
     * `inline-end` means opposite sides two elements apart. Everything else in
     * this file is physical pixels already; the drawing is.
     *
     * Set here rather than in the stylesheet because the lane is measured from
     * the numbers as they render, on every draw, and CSS cannot know it. The
     * surface is what the chart measures itself from and this is its child, so
     * narrowing it feeds nothing back.
     */
    scroller.style.marginRight = `${box.padding.value}px`;
    const minimumBand = isCompact ? MIN_BAND_COMPACT : isNarrow ? MIN_BAND_NARROW : MIN_BAND;
    // Exactly the viewport while the columns fit it: the geometry below is then
    // identical to what this chart drew before it could scroll at all, so a
    // series short enough to fit is laid out to the pixel as it always was.
    const contentWidth = Math.max(
      viewportWidth,
      Math.ceil(points.length * minimumBand) + box.padding.far + EDGE_GUTTER,
    );
    const scrolls = contentWidth > viewportWidth;
    const drawHeight = Math.max(height - (scrolls ? SCROLLBAR_ALLOWANCE : 0), MIN_HEIGHT);

    const plotWidth = Math.max(contentWidth - box.padding.far - EDGE_GUTTER, 40);
    const plotHeight = Math.max(drawHeight - box.padding.top - box.padding.bottom, 40);
    const plotTop = box.padding.top;
    const plotBottom = plotTop + plotHeight;
    const plotRight = contentWidth - EDGE_GUTTER;
    const bandWidth = points.length ? plotWidth / points.length : plotWidth;

    const root = svg("svg", {
      class: "combo-chart__svg",
      width: contentWidth,
      height: drawHeight,
      role: "img",
      "aria-label": ariaLabel,
      focusable: "false",
    });

    // The SVG is stretched to the surface, so a tick's y is the same number of
    // CSS pixels down from its top and the numbers land on their own lines.
    ticks.forEach((tick, index) => {
      const y = plotBottom - (plotHeight * tick.magnitude) / 100;
      root.append(svg("line", { class: "combo-chart__gridline", x1: plotRight - plotWidth, x2: plotRight, y1: y, y2: y }));
      const node = axis.nodes[index];
      // Pinned to the lane's OUTER edge, not to a left computed from the width.
      // `width` above has a 240px floor for a surface that has not been laid out
      // yet, and on a surface genuinely narrower than that the floor put these
      // numbers past the card's edge — measured at 320px, 13px outside it. The
      // right edge is a real coordinate at every width, and pinning to it also
      // lines the numbers up as a column instead of ragging them against the
      // card. The clear space to the plot is then the lane's own width minus the
      // widest number, which is `axisGap` by construction.
      node.style.left = "auto";
      node.style.right = `${box.axisEdge}px`;
      node.style.top = `${y}px`;
    });

    const barWidth = bandWidth * box.barWidthRatio;
    /**
     * Where a month is drawn: TIME RUNS LEFT TO RIGHT.
     *
     * Not the page's reading order, and deliberately so. A time axis is read as
     * a line from the beginning of the project to now, and every other chart a
     * reader of this one has seen -- the schedule's own S-curve included -- runs
     * that line the same way. The months are the axis here, not text, so they
     * follow the axis convention rather than the script's.
     *
     * The value axis keeps its own place at the reading start, on the right.
     */
    const plotLeft = plotRight - plotWidth;
    const centreOf = (index) => plotLeft + bandWidth * (index + 0.5);

    points.forEach((point, index) => {
      const centre = centreOf(index);
      // The baseline is the bottom of the plot and stays there. A magnitude is
      // never negative, so a bar never grows downward out of it.
      const barHeight = (plotHeight * point[barSeries.magnitudeKey]) / 100;
      if (barHeight > 0) {
        root.append(svg("rect", {
          class: "combo-chart__bar",
          x: centre - barWidth / 2,
          y: plotBottom - barHeight,
          width: barWidth,
          height: barHeight,
          rx: Math.min(4, barWidth / 3),
        }));
      }
      const anchorY = plotBottom + CATEGORY_GAP;
      const category = svg("text", {
        class: "combo-chart__category",
        x: centre,
        y: anchorY,
        "font-size": box.fontSize,
        // The leading edge — the right one, in this script, which the
        // stylesheet fixes rather than leaving to whatever the label's own
        // characters resolve to. The word therefore starts under its own band
        // and trails away from it instead of across its neighbour.
        "text-anchor": "start",
        transform: `rotate(${CATEGORY_TILT} ${centre} ${anchorY})`,
      });
      category.textContent = categoryTextOf(point);
      root.append(category);
    });

    // The estimate line breaks into segments so a month without a baseline
    // leaves a visible gap instead of an invented straight run.
    const lineNodes = points.map((point, index) => {
      const value = point[lineSeries.magnitudeKey];
      return value === null || value === undefined
        ? null
        : { x: centreOf(index), y: plotBottom - (plotHeight * value) / 100 };
    });
    let segment = [];
    const flushSegment = () => {
      if (segment.length > 1) {
        root.append(svg("polyline", { class: "combo-chart__line", points: segment.map((node) => `${node.x},${node.y}`).join(" ") }));
      }
      segment = [];
    };
    lineNodes.forEach((node) => {
      if (node) segment.push(node);
      else flushSegment();
    });
    flushSegment();
    lineNodes.forEach((node) => {
      if (node) root.append(svg("circle", { class: "combo-chart__marker", cx: node.x, cy: node.y, r: isCompact ? 2.6 : 3.2 }));
    });

    root.append(svg("line", { class: "combo-chart__baseline", x1: plotRight - plotWidth, x2: plotRight, y1: plotBottom, y2: plotBottom }));

    points.forEach((point, index) => {
      const centre = centreOf(index);
      const hit = svg("rect", {
        class: "combo-chart__hit",
        x: centre - bandWidth / 2,
        y: plotTop,
        width: bandWidth,
        height: plotHeight,
        "data-centre": centre,
        "data-index": index,
      });
      root.append(hit);
    });

    // Width only. Height stays with the stylesheet, at 100% of the lane, because
    // the drawing is measured FROM its container: a pixel height here made the
    // container as tall as the drawing, which made the next measurement taller
    // still. On a panel with a height of its own the loop is invisible; on this
    // page, whose panel sizes to its content, it ran to a 130,808px chart.
    root.style.inlineSize = `${contentWidth}px`;
    // Replacing the scrolled content resets the scroll, and a redraw is not a
    // reason to move the reader: the ResizeObserver fires on any layout change —
    // revealing the panel, appearing scrollbar, rotating the device — and each
    // one used to throw away where they had scrolled to.
    const previousScroll = scroller.scrollLeft;
    scroller.replaceChildren(root);
    // The axis layer goes back with the rest: it has to stay in the document to
    // be measurable on the next draw.
    surface.replaceChildren(scroller, tooltip, axisLayer);
    if (pendingScrollReset) {
      // Centre the focus column in the first visible frame. For the monthly
      // trend this is today's month, so opening or revealing a long project
      // never starts on an arbitrary edge. The browser clamps the offset when
      // there is not enough content on either side to keep it centred.
      const focusLeft = focusIndex >= 0
        ? Math.max(centreOf(focusIndex) - viewportWidth / 2, 0)
        // No month of the window is the one the reader is in — the project has
        // ended, or has not started. The newest month is then the right answer,
        // and it is at the far end of the scroll.
        : contentWidth;
      scroller.scrollLeft = focusLeft;
      // And again once the browser has measured the drawing it was just given.
      // A scroll offset assigned to a box with no laid-out overflow is clamped
      // to zero, so this first assignment can silently do nothing — which is how
      // the chart came to open on the wrong month depending on how the frame
      // happened to fall.
      requestAnimationFrame(() => {
        if (!pendingScrollReset || destroyed) return;
        scroller.scrollLeft = focusLeft;
        // Settled only when the offset was computed against a real width. Until
        // then the reveal is still to come, and it has to be free to place the
        // reader again.
        if (measured) pendingScrollReset = false;
      });
    } else {
      scroller.scrollLeft = previousScroll;
    }
    if (activeIndex >= 0 && points[activeIndex]) {
      const hit = root.querySelector(`.combo-chart__hit[data-index="${activeIndex}"]`);
      if (hit) showTooltip(activeIndex, hit);
      else hideTooltip();
    }
  }

  function onPointer(event) {
    const hit = event.target.closest?.(".combo-chart__hit");
    // Anywhere inside the surface that is not a column closes the panel. The
    // axis numbers sit over the plot with their own tooltip, and leaving the
    // column's open underneath would put two on the screen at once.
    if (!hit) {
      hideTooltip();
      return;
    }
    showTooltip(Number(hit.getAttribute("data-index")), hit);
  }

  // An open panel is anchored to a column. Scrolling moves the column out from
  // under it, so the panel follows or goes.
  scroller.addEventListener("scroll", () => {
    if (activeIndex < 0) return;
    const hit = scroller.querySelector(`.combo-chart__hit[data-index="${activeIndex}"]`);
    if (hit) showTooltip(activeIndex, hit);
    else hideTooltip();
  });

  surface.addEventListener("pointermove", onPointer);
  surface.addEventListener("pointerdown", onPointer);
  surface.addEventListener("pointerleave", hideTooltip);

  return Object.freeze({
    element: container,

    /**
     * `focusColumn` names the point the chart should open on - the current month
     * for a series that runs past it. Out of range or absent, the chart opens on
     * the latest available point.
     */
    setData({ points: nextPoints = [], ticks: nextTicks = [], focusColumn = -1 } = {}) {
      points = nextPoints;
      ticks = nextTicks;
      focusIndex = Number.isInteger(focusColumn) && focusColumn >= 0 && focusColumn < points.length
        ? focusColumn
        : -1;
      activeIndex = -1;
      tooltip.hidden = true;
      pendingScrollReset = true;
      draw();
      if (!observer && typeof ResizeObserver === "function") {
        observer = new ResizeObserver(() => {
          if (!container.isConnected) {
            observer?.disconnect();
            observer = null;
            return;
          }
          draw();
        });
        observer.observe(surface);
      }
    },

    /**
     * Redraws against the container's current width. A chart built inside a
     * hidden panel measures zero, so the panel that reveals it calls this.
     */
    resize() {
      draw();
    },

    /**
     * Redraw and return to the configured focus column. Unlike `resize`, this
     * deliberately discards a previous scroll offset and is used whenever a
     * hidden chart is selected again.
     */
    resetView() {
      pendingScrollReset = true;
      hideTooltip();
      draw();
    },

    destroy() {
      destroyed = true;
      observer?.disconnect();
      observer = null;
      surface.removeEventListener("pointermove", onPointer);
      surface.removeEventListener("pointerdown", onPointer);
      surface.removeEventListener("pointerleave", hideTooltip);
      container.replaceChildren();
    },
  });
}
