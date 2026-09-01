import { element } from "../dom/elements.js";
import { curvePath } from "../charts/cost-curve.js";

/**
 * The cumulative cost curve, drawn the way the host platform draws its progress
 * S-curve: a dashed plan running the full width, a filled actual stopping at
 * today, and a marker calling out where it stopped.
 *
 * The value guide is HTML positioned over the plot rather than SVG `<text>`.
 * That is not a preference — SVG text cannot carry CSS generated content, and
 * the guide's exact-amount tooltip is the same `::after` the other charts in
 * this module use. Keeping it in HTML keeps one tooltip mechanism site-wide.
 */

const SVG_NS = "http://www.w3.org/2000/svg";
const MIN_HEIGHT = 140;
const NARROW_WIDTH = 560;

function svg(tag, attributes = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  Object.entries(attributes).forEach(([name, value]) => {
    if (value !== null && value !== undefined) node.setAttribute(name, String(value));
  });
  return node;
}

/**
 * The plot box inside the surface. The guide lane is measured from the rendered
 * labels rather than guessed, so a project whose amounts run to twelve digits
 * gets the room it needs and a small one does not pay for room it doesn't use.
 *
 * Everything here is in physical left-to-right coordinates, and so is every
 * overlay the component positions. SVG has no writing direction — it draws in
 * physical space whatever the page's `dir` is — so an overlay positioned with
 * `inset-inline-*` on an RTL page lands mirrored against the curve it labels.
 * Time therefore runs left to right, the guide sits on the left, and the whole
 * chart matches the progress S-curve the host platform already issues.
 */
function geometry(width, height, guideWidth, isNarrow) {
  const gap = isNarrow ? 8 : 12;
  const lane = Math.max(Math.min(Math.ceil(guideWidth) + gap, Math.floor(width * 0.32)), 28);
  const labelBand = isNarrow ? 22 : 26;
  // Room above the top gridline for two things that must not collide with it:
  // the guide's unit on the left, and the marker's callout wherever it lands.
  const headroom = isNarrow ? 24 : 30;
  return {
    left: lane,
    lane,
    top: headroom,
    bottom: labelBand,
    // A margin at the far end: the last period's label is centred on its point
    // and the marker usually sits there, so without it both hang off the edge.
    innerWidth: Math.max(width - lane - (isNarrow ? 16 : 26), 10),
    innerHeight: Math.max(height - headroom - labelBand, 10),
  };
}

export function createCostCurveChart({
  formatValue = () => "",
  formatExactValue = () => "",
  formatMarker = () => "",
  ariaLabel = "منحنی تجمعی هزینه پروژه",
  planLabel = "برنامه (هدف)",
  unitLabel = "",
} = {}) {
  const root = element("div", "cost-curve");
  const surface = element("div", "cost-curve__surface");
  surface.setAttribute("role", "img");
  surface.setAttribute("aria-label", ariaLabel);
  const guideLayer = element("div", "cost-curve__guide");
  surface.append(guideLayer);
  root.append(surface);

  let view = null;
  let frame = null;

  /**
   * Lays the guide out once so its widest label can be measured.
   *
   * `scale` is what the drawing is squashed by. The canvas is drawn in a space
   * at least MIN_HEIGHT tall and then stretched to the surface with
   * `preserveAspectRatio: none`, so in a surface shorter than that every
   * gridline lands at a fraction of where it was drawn. These labels are HTML,
   * not SVG, and nothing scales them — so they are placed in the squashed space
   * the reader actually sees, or a label names a line it is no longer beside.
   */
  function layoutGuide(box, ticks, scale = 1) {
    const nodes = ticks.map((tick) => {
      const node = element("span", "cost-curve__guide-value", formatValue(tick.valueIrr));
      const exact = formatExactValue(tick.valueIrr);
      if (exact) node.dataset.exact = exact;
      node.style.setProperty("--tick", `${tick.magnitude}`);
      return node;
    });
    // The unit is said once, at the head of the lane, rather than repeated on
    // every line — the same way the monthly chart labels its own guide.
    const unit = unitLabel ? [element("span", "cost-curve__guide-unit", unitLabel)] : [];
    guideLayer.replaceChildren(...unit, ...nodes);
    const widest = nodes.reduce((result, node) => Math.max(result, node.offsetWidth), 0);
    if (box) {
      guideLayer.style.setProperty("--plot-top", `${box.top * scale}px`);
      guideLayer.style.setProperty("--plot-height", `${box.innerHeight * scale}px`);
      guideLayer.style.setProperty("--lane", `${box.lane}px`);
    }
    return widest;
  }

  function draw() {
    frame = null;
    if (!view || view.isEmpty) {
      surface.replaceChildren(guideLayer);
      return;
    }

    const width = surface.clientWidth;
    if (!width) return;
    const height = Math.max(surface.clientHeight, MIN_HEIGHT);
    const isNarrow = width < NARROW_WIDTH;

    // Measured, then laid out again once the box that depends on it is known.
    const widest = layoutGuide(null, view.ticks);
    const box = geometry(width, height, widest, isNarrow);
    layoutGuide(box, view.ticks, (surface.clientHeight || height) / height);

    const canvas = svg("svg", {
      class: "cost-curve__canvas",
      viewBox: `0 0 ${width} ${height}`,
      preserveAspectRatio: "none",
      focusable: "false",
      "aria-hidden": "true",
    });

    /* 0–100 chart space to pixels. y is measured from the bottom.
       The curve is rebuilt in pixel space rather than the model's path being
       rewritten: monotone interpolation survives the flip (negation is itself
       monotone), and it keeps one code path for the geometry. */
    const px = (x) => box.left + (x / 100) * box.innerWidth;
    const py = (y) => box.top + box.innerHeight - (y / 100) * box.innerHeight;
    const project = (points) => points.map((point) => ({ x: px(point.x), y: py(point.y) }));

    const grid = svg("g", { class: "cost-curve__grid" });
    view.ticks.forEach((tick) => {
      const y = py(tick.magnitude);
      grid.append(svg("line", {
        x1: box.left, x2: box.left + box.innerWidth, y1: y, y2: y,
        class: tick.magnitude === 0 ? "cost-curve__baseline" : "cost-curve__gridline",
      }));
    });
    canvas.append(grid);

    const actualPixels = project(view.actual);
    const planPixels = project(view.plan);
    const actualPath = curvePath(actualPixels);
    const baseline = py(0);

    if (actualPixels.length > 1) {
      const first = actualPixels[0];
      const last = actualPixels[actualPixels.length - 1];
      canvas.append(svg("path", {
        // The fill is the curve itself closed down to the baseline, so its top
        // edge can never drift from the line it belongs to.
        d: `${actualPath} L ${last.x.toFixed(2)} ${baseline.toFixed(2)} L ${first.x.toFixed(2)} ${baseline.toFixed(2)} Z`,
        class: "cost-curve__area",
      }));
    }
    if (planPixels.length) {
      canvas.append(svg("path", { d: curvePath(planPixels), class: "cost-curve__plan" }));
    }
    if (actualPath) {
      canvas.append(svg("path", { d: actualPath, class: "cost-curve__actual" }));
    }

    if (view.marker) {
      const x = px(view.marker.x);
      const y = py(view.marker.y);
      const stem = svg("g", { class: "cost-curve__marker" });
      stem.append(svg("line", { x1: x, x2: x, y1: box.top, y2: box.top + box.innerHeight, class: "cost-curve__marker-line" }));
      stem.append(svg("circle", { cx: x, cy: y, r: 4, class: "cost-curve__marker-dot" }));
      canvas.append(stem);
    }

    surface.replaceChildren(canvas, guideLayer);

    // The callout is HTML so it inherits the module's Persian numerals and can
    // be read by the same tooltip rules as everything else on the page.
    if (view.marker) {
      const callout = element("span", "cost-curve__callout", formatMarker(view.marker.valueIrr));
      const at = px(view.marker.x);
      // Centred over its marker, except near the end of the plot — which is
      // where it normally sits, because the actual series stops at today — so
      // it tucks in against the edge instead of hanging off it.
      const nearEnd = at > box.left + box.innerWidth * 0.72;
      callout.style.left = `${at}px`;
      callout.style.transform = nearEnd ? "translateX(-100%)" : "translateX(-50%)";
      callout.style.paddingInlineEnd = nearEnd ? "6px" : "0";
      callout.style.top = `${Math.max(box.top - 20, 0)}px`;
      surface.append(callout);
    }

    const labels = element("div", "cost-curve__periods");
    view.periods.forEach((period) => {
      const label = element("span", "cost-curve__period", isNarrow ? period.shortLabel : period.label);
      label.style.left = `${px(period.x)}px`;
      label.title = period.fullLabel;
      labels.append(label);
    });
    labels.style.setProperty("--band", `${box.bottom}px`);
    surface.append(labels);

    if (!view.hasPlan) {
      const absent = element("p", "cost-curve__absent",
        `${planLabel} هنوز از فایل‌های دوره‌ای میزبان دریافت نشده و منحنی برنامه رسم نشده است.`);
      absent.setAttribute("role", "status");
      root.replaceChildren(surface, absent);
    } else {
      root.replaceChildren(surface);
    }
  }

  function schedule() {
    if (frame !== null) return;
    frame = requestAnimationFrame(draw);
  }

  const observer = typeof ResizeObserver === "function" ? new ResizeObserver(schedule) : null;
  observer?.observe(surface);

  return Object.freeze({
    element: root,
    setData(next) {
      view = next;
      schedule();
    },
    resize: schedule,
    destroy() {
      observer?.disconnect();
      if (frame !== null) cancelAnimationFrame(frame);
    },
  });
}
