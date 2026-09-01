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
function geometry(width, height, isNarrow, isCompact, axisWidth) {
  const barWidthRatio = isCompact ? 0.52 : 0.44;
  // A short box spends a punishing share of itself on padding, so trim the top
  // (which only holds air) and keep the bottom, which carries the month labels.
  const isShort = height < 200;
  const gap = isCompact ? 9 : 13;
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
      bottom: 30,
      far: isCompact ? 10 : 16,
    },
    axisGap: gap,
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
  surface.append(tooltip, axisLayer);

  /** Renders the axis numbers and answers how wide the widest of them is. */
  function layoutAxis(fontSize) {
    const nodes = ticks.map((tick) => {
      const shown = formatValue(tick.valueIrr) ?? "";
      const exact = formatExactValue?.(tick.valueIrr);
      const node = element("span", `combo-chart__axis-value numeric${exact ? " compact-money" : ""}`, shown);
      node.style.fontSize = `${fontSize}px`;
      if (exact) {
        node.dataset.exact = exact;
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
    const bandCentre = Number(hit.getAttribute("data-centre"));
    // Measured against the start of the surface, then placed: the panel's own
    // width is only known once it is somewhere definite.
    tooltip.style.left = "0px";
    const panelWidth = tooltip.offsetWidth;
    const left = Math.min(Math.max(bandCentre - panelWidth / 2, 4), Math.max(surfaceWidth - panelWidth - 4, 4));
    tooltip.style.left = `${left}px`;
  }

  function draw() {
    if (destroyed) return;
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
    const height = available > 0 ? available : Math.max(fallback, MIN_HEIGHT);
    const fontSize = isCompact ? 9 : isNarrow ? 10 : 11;
    const axis = layoutAxis(fontSize);
    const box = geometry(width, height, isNarrow, isCompact, axis.widest);
    const plotWidth = Math.max(box.width - box.padding.value - box.padding.far, 40);
    const plotHeight = Math.max(box.height - box.padding.top - box.padding.bottom, 40);
    const plotTop = box.padding.top;
    const plotBottom = plotTop + plotHeight;
    // RTL: category 0 sits at the right edge and the series advance leftwards.
    const plotRight = box.width - box.padding.value;
    const bandWidth = points.length ? plotWidth / points.length : plotWidth;

    const root = svg("svg", {
      class: "combo-chart__svg",
      width: box.width,
      height: box.height,
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
      node.style.left = `${plotRight + box.axisGap}px`;
      node.style.top = `${y}px`;
    });

    const barWidth = bandWidth * box.barWidthRatio;
    const centreOf = (index) => plotRight - bandWidth * (index + 0.5);

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
      const category = svg("text", {
        class: "combo-chart__category",
        x: centre,
        y: plotBottom + box.fontSize + 8,
        "font-size": box.fontSize,
        "text-anchor": "middle",
      });
      category.textContent = isNarrow ? point[narrowCategoryKey] : point[categoryKey];
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

    // The axis layer goes back with the rest: it has to stay in the document to
    // be measurable on the next draw.
    surface.replaceChildren(root, tooltip, axisLayer);
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

  surface.addEventListener("pointermove", onPointer);
  surface.addEventListener("pointerdown", onPointer);
  surface.addEventListener("pointerleave", hideTooltip);

  return Object.freeze({
    element: container,

    setData({ points: nextPoints = [], ticks: nextTicks = [] } = {}) {
      points = nextPoints;
      ticks = nextTicks;
      activeIndex = -1;
      tooltip.hidden = true;
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
