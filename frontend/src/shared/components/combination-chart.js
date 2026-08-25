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

function geometry(width, height, isNarrow, isCompact) {
  const barWidthRatio = isCompact ? 0.52 : 0.44;
  // A short box spends a punishing share of itself on padding, so trim the top
  // (which only holds air) and keep the bottom, which carries the month labels.
  const isShort = height < 200;
  return {
    width,
    height,
    padding: {
      // Inline-start of an RTL chart is the right edge, where the value axis
      // sits. Labels are short numbers on one shared scale, so this is enough.
      value: isCompact ? 34 : 44,
      top: isShort ? 8 : 16,
      bottom: 30,
      far: isCompact ? 10 : 16,
    },
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
  renderTooltip,
  ariaLabel = "نمودار ترکیبی",
} = {}) {
  const container = element("div", "combo-chart");
  const surface = element("div", "combo-chart__surface");
  const tooltip = element("div", "combo-chart__tooltip");
  tooltip.setAttribute("role", "status");
  tooltip.hidden = true;
  surface.append(tooltip);
  container.append(surface);

  let points = [];
  let ticks = [];
  // Where the value zero sits on the axis, 0 at the bottom of the plot and 100
  // at the top. It only moves off the bottom when a series goes below zero.
  let zeroMagnitude = 0;
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
    tooltip.style.insetInlineStart = "auto";
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
    const box = geometry(width, height, isNarrow, isCompact);
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

    ticks.forEach((tick) => {
      const y = plotBottom - (plotHeight * tick.magnitude) / 100;
      root.append(svg("line", { class: "combo-chart__gridline", x1: plotRight - plotWidth, x2: plotRight, y1: y, y2: y }));
      const label = svg("text", {
        class: "combo-chart__axis-label",
        x: plotRight + 8,
        y: y + box.fontSize / 3,
        "font-size": box.fontSize,
        "text-anchor": "start",
      });
      label.textContent = formatValue(tick.valueIrr);
      root.append(label);
    });

    const barWidth = bandWidth * box.barWidthRatio;
    const centreOf = (index) => plotRight - bandWidth * (index + 0.5);
    // Bars grow from the value zero, which is at the bottom of the plot unless
    // some point went below it. A month whose reversals outweigh its purchases
    // hangs below the line rather than standing as tall as a month that spent
    // the same amount.
    const zeroY = plotBottom - (plotHeight * zeroMagnitude) / 100;

    points.forEach((point, index) => {
      const centre = centreOf(index);
      const valueY = plotBottom - (plotHeight * point[barSeries.magnitudeKey]) / 100;
      const barHeight = Math.abs(valueY - zeroY);
      if (barHeight > 0) {
        root.append(svg("rect", {
          class: `combo-chart__bar${valueY > zeroY ? " combo-chart__bar--negative" : ""}`,
          x: centre - barWidth / 2,
          y: Math.min(valueY, zeroY),
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
    // With anything below zero the bottom of the plot is no longer the value
    // zero, so the line the bars are measured from has to be drawn where it is.
    if (Math.abs(zeroY - plotBottom) > 0.5) {
      root.append(svg("line", { class: "combo-chart__zero-line", x1: plotRight - plotWidth, x2: plotRight, y1: zeroY, y2: zeroY }));
    }

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

    surface.replaceChildren(root, tooltip);
    if (activeIndex >= 0 && points[activeIndex]) {
      const hit = root.querySelector(`.combo-chart__hit[data-index="${activeIndex}"]`);
      if (hit) showTooltip(activeIndex, hit);
      else hideTooltip();
    }
  }

  function onPointer(event) {
    const hit = event.target.closest?.(".combo-chart__hit");
    if (!hit) {
      if (event.type === "pointerdown") hideTooltip();
      return;
    }
    showTooltip(Number(hit.getAttribute("data-index")), hit);
  }

  surface.addEventListener("pointermove", onPointer);
  surface.addEventListener("pointerdown", onPointer);
  surface.addEventListener("pointerleave", hideTooltip);

  return Object.freeze({
    element: container,

    setData({ points: nextPoints = [], ticks: nextTicks = [], zeroMagnitude: nextZero = 0 } = {}) {
      points = nextPoints;
      ticks = nextTicks;
      zeroMagnitude = Number.isFinite(nextZero) ? nextZero : 0;
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
