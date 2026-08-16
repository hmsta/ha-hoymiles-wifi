(() => {
  "use strict";

  const CARD_TYPE = "hoymiles-layout-card";
  const DEFAULT_ASPECT = 1.861;
  const DEFAULT_MAX_WATTS = 300;
  const DEFAULT_OFF_THRESHOLD_WATTS = 1;
  const DEFAULT_MAX_ZOOM = 15;
  const DEFAULT_REPLAY_STEP_SECONDS = 60 * 60;
  const DEFAULT_REPLAY_START_HOUR = 6;
  const DEFAULT_REPLAY_END_HOUR = 19;
  const DEFAULT_HISTORY_BATCH_SIZE = 80;
  const REPLAY_CACHE_TTL_MS = 5 * 60 * 1000;
  const TAP_MOVE_THRESHOLD_PX = 8;
  const DEFAULT_CROP_X = 0.5;
  const DEFAULT_CROP_Y = 1;

  const css = `
    :host {
      display: block;
      width: 100%;
      height: 100%;
      --hoymiles-map-aspect: ${DEFAULT_ASPECT};
      --hoymiles-map-min-height: 420px;
      --hoymiles-panel-bg: #101923;
      --hoymiles-panel-frame-color: rgba(215, 221, 230, .88);
      --hoymiles-panel-fill-color: rgba(33, 151, 231, .82);
      --hoymiles-panel-grid: rgba(255, 255, 255, .16);
    }

    * {
      box-sizing: border-box;
    }

    ha-card {
      overflow: hidden;
      width: 100%;
      height: 100%;
    }

    .map {
      position: relative;
      width: 100%;
      height: var(--hoymiles-map-height, auto);
      aspect-ratio: var(--hoymiles-map-aspect) / 1;
      min-height: var(--hoymiles-map-min-height);
      background: #0b0d10;
      overflow: hidden;
      cursor: grab;
      touch-action: none;
      user-select: none;
    }

    .map.dragging {
      cursor: grabbing;
    }

    .modeToggle {
      position: absolute;
      right: 8px;
      top: 8px;
      z-index: 4;
      display: flex;
      gap: 2px;
      padding: 3px;
      border-radius: 8px;
      background: rgba(8, 12, 18, .62);
      backdrop-filter: blur(8px);
      pointer-events: auto;
    }

    .modeToggle button {
      min-width: 36px;
      border: 0;
      border-radius: 6px;
      padding: 5px 8px;
      background: transparent;
      color: rgba(255, 255, 255, .76);
      font: 700 12px/1 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      cursor: pointer;
    }

    .modeToggle button.active {
      background: rgba(33, 151, 231, .82);
      color: white;
    }

    .modeToggle[hidden] {
      display: none;
    }

    .replayButton {
      position: absolute;
      left: 8px;
      top: 8px;
      z-index: 4;
      min-width: 60px;
      border: 0;
      border-radius: 8px;
      padding: 8px 10px;
      background: rgba(8, 12, 18, .62);
      color: rgba(255, 255, 255, .86);
      font: 700 12px/1 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      backdrop-filter: blur(8px);
      cursor: pointer;
      pointer-events: auto;
    }

    .replayButton.active {
      background: rgba(33, 151, 231, .84);
      color: white;
    }

    .replayButton[hidden] {
      display: none;
    }

    .replayScrubber {
      position: absolute;
      left: 10px;
      right: 10px;
      bottom: 10px;
      z-index: 4;
      display: grid;
      grid-template-columns: auto minmax(0, 1fr) auto;
      align-items: center;
      gap: 8px;
      padding: 8px 10px;
      border-radius: 10px;
      background: rgba(8, 12, 18, .72);
      color: white;
      backdrop-filter: blur(10px);
      pointer-events: auto;
      touch-action: pan-x;
    }

    .replayScrubber[hidden] {
      display: none;
    }

    .replayScrubber button {
      border: 0;
      border-radius: 7px;
      padding: 8px 10px;
      background: rgba(255, 255, 255, .16);
      color: white;
      font: 700 12px/1 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      cursor: pointer;
    }

    .replayScrubber input[type="range"] {
      width: 100%;
      min-width: 0;
      accent-color: rgb(33, 151, 231);
      touch-action: pan-x;
    }

    .replayTime {
      min-width: 42px;
      color: rgba(255, 255, 255, .9);
      font: 700 11px/1 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      text-align: right;
      white-space: nowrap;
    }

    .cameraLayer {
      position: absolute;
      transform-origin: center center;
      will-change: transform;
    }

    .background {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      object-fit: fill;
      pointer-events: none;
      user-select: none;
    }

    .overlay {
      position: absolute;
      inset: 0;
      pointer-events: none;
    }

    .panelRow {
      position: absolute;
      left: 0;
      top: 0;
      overflow: visible;
      pointer-events: none;
      transform-origin: center center;
    }

    .panelItem {
      --panel-font: 8px;
      --panel-id-font: 3px;
      --metric-rotation: 0deg;
      --panel-frame: .22%;
      --panel-radius: .35%;
      --panel-fill: 0%;
      --panel-fill-angle: 90deg;
      position: absolute;
      left: 0;
      top: 0;
      display: grid;
      place-items: center;
      border: 0;
      border-radius: var(--panel-radius);
      background: transparent;
      color: white;
      font-weight: 700;
      line-height: 1;
      text-align: center;
      text-shadow: 0 1px 2px rgba(0, 0, 0, .7);
      overflow: hidden;
      transform-origin: center center;
      pointer-events: auto;
      isolation: isolate;
    }

    .panelItem::before {
      content: "";
      position: absolute;
      inset: 0;
      z-index: 0;
      background: var(--hoymiles-panel-bg);
    }

    .panelFill {
      position: absolute;
      left: 0;
      top: 0;
      z-index: 1;
      width: var(--panel-fill);
      height: 100%;
      background: var(--hoymiles-panel-fill-color);
      pointer-events: none;
    }

    .panelFill.vertical {
      width: 100%;
      height: var(--panel-fill);
      top: auto;
      bottom: 0;
    }

    .panelItem::after {
      content: "";
      position: absolute;
      inset: 0;
      z-index: 2;
      pointer-events: none;
      background:
        linear-gradient(var(--hoymiles-panel-frame-color), var(--hoymiles-panel-frame-color)) 0 0 / 100% var(--panel-frame) no-repeat,
        linear-gradient(var(--hoymiles-panel-frame-color), var(--hoymiles-panel-frame-color)) 0 100% / 100% var(--panel-frame) no-repeat,
        linear-gradient(var(--hoymiles-panel-frame-color), var(--hoymiles-panel-frame-color)) 0 0 / var(--panel-frame) 100% no-repeat,
        linear-gradient(var(--hoymiles-panel-frame-color), var(--hoymiles-panel-frame-color)) 100% 0 / var(--panel-frame) 100% no-repeat,
        repeating-linear-gradient(90deg, transparent 0 23%, var(--hoymiles-panel-grid) 23% 24%, transparent 24% 25%),
        repeating-linear-gradient(0deg, transparent 0 18%, var(--hoymiles-panel-grid) 18% 19%, transparent 19% 20%);
    }

    .panelItem.off {
      --hoymiles-panel-bg: #101923;
      --hoymiles-panel-grid: rgba(255, 255, 255, .11);
    }

    .signalMarker {
      --signal-font: 12px;
      --signal-icon: 11px;
      position: absolute;
      left: 0;
      top: 0;
      z-index: 3;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: calc(var(--signal-font) * .22);
      min-width: max-content;
      padding: calc(var(--signal-font) * .26) calc(var(--signal-font) * .38);
      border: 1px solid rgba(215, 221, 230, .48);
      border-radius: calc(var(--signal-font) * .38);
      background: rgba(12, 20, 29, .82);
      color: white;
      font: 800 var(--signal-font)/1 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      text-shadow: 0 1px 2px rgba(0, 0, 0, .75);
      transform: translate(-50%, -50%);
      transform-origin: center center;
      pointer-events: auto;
      white-space: nowrap;
    }

    .signalMarker.off {
      color: rgba(255, 255, 255, .72);
      background: rgba(12, 20, 29, .66);
    }

    .signalIcon {
      width: var(--signal-icon);
      height: var(--signal-icon);
      flex: 0 0 var(--signal-icon);
      color: rgba(33, 151, 231, .94);
    }

    .signalMarker.weak .signalIcon {
      color: rgba(255, 181, 71, .95);
    }

    .signalMarker.rssiOk .signalIcon {
      color: rgba(39, 194, 107, .96);
    }

    .signalMarker.rssiWarn .signalIcon {
      color: rgba(255, 181, 71, .95);
    }

    .signalMarker.rssiBad .signalIcon {
      color: rgba(244, 82, 92, .97);
    }

    .signalMarker.off .signalIcon {
      color: rgba(255, 255, 255, .52);
    }

    .signalValue {
      display: inline-block;
    }

    .panelTextStack {
      position: absolute;
      z-index: 3;
      left: 62%;
      top: 57%;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: calc(var(--panel-font) * .08);
      transform: translate(-50%, -50%) rotate(var(--metric-rotation));
      transform-origin: center;
      white-space: nowrap;
    }

    .panelMetric {
      display: grid;
      gap: 0;
      place-items: center;
    }

    .panelMetric .value {
      font-size: calc(var(--panel-font) * .82);
      line-height: .9;
    }

    .panelId {
      color: rgba(255, 255, 255, .86);
      font-size: var(--panel-id-font);
      font-weight: 600;
      line-height: .9;
      opacity: .84;
      white-space: nowrap;
    }

    .mapError {
      position: absolute;
      inset: 0;
      display: grid;
      place-items: center;
      padding: 24px;
      color: var(--error-color, #ffc9c9);
      background: rgba(8, 10, 12, .9);
      text-align: center;
      z-index: 5;
    }
  `;

  function fireEvent(node, type, detail = {}, options = {}) {
    const event = new CustomEvent(type, {
      detail,
      bubbles: options.bubbles !== false,
      cancelable: Boolean(options.cancelable),
      composed: options.composed !== false,
    });
    node.dispatchEvent(event);
    return event;
  }

  function maybeJson(value) {
    if (typeof value !== "string") return value;
    try {
      return JSON.parse(value);
    } catch {
      return value;
    }
  }

  function asObject(value) {
    const parsed = maybeJson(value);
    return parsed && typeof parsed === "object" ? parsed : {};
  }

  function numericValue(value) {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string") {
      const cleaned = value.replace(",", ".").replace(/[^\d.+-]/g, "");
      if (!/\d/.test(cleaned)) return null;
      const parsed = Number(cleaned);
      return Number.isFinite(parsed) ? parsed : null;
    }
    return null;
  }

  function optionalNumber(value, fallback = null) {
    if (value === false || value === null || value === undefined || value === "") {
      return fallback;
    }
    const parsed = numericValue(value);
    return parsed == null ? fallback : parsed;
  }

  function optionalReplayHour(value, fallback) {
    if (value === false || value === null || value === undefined || value === "") {
      return fallback;
    }
    if (typeof value === "string") {
      const trimmed = value.trim().toLowerCase();
      const amPmMatch = trimmed.match(/^(\d{1,2})(?::(\d{1,2}))?\s*(am|pm)$/);
      if (amPmMatch) {
        let hours = Number(amPmMatch[1]);
        const minutes = Number(amPmMatch[2] || 0);
        if (
          Number.isFinite(hours)
          && Number.isFinite(minutes)
          && hours >= 1
          && hours <= 12
          && minutes >= 0
          && minutes < 60
        ) {
          if (amPmMatch[3] === "pm" && hours !== 12) hours += 12;
          if (amPmMatch[3] === "am" && hours === 12) hours = 0;
          return Math.min(24, Math.max(0, hours + minutes / 60));
        }
        return fallback;
      }

      const match = trimmed.match(/^(\d{1,2}):(\d{1,2})$/);
      if (match) {
        const hours = Number(match[1]);
        const minutes = Number(match[2]);
        if (
          Number.isFinite(hours)
          && Number.isFinite(minutes)
          && hours >= 0
          && hours <= 24
          && minutes >= 0
          && minutes < 60
        ) {
          return Math.min(24, Math.max(0, hours + minutes / 60));
        }
      }
    }
    const parsed = optionalNumber(value, fallback);
    return Math.min(24, Math.max(0, parsed));
  }

  function setDateHour(date, hour) {
    const wholeHours = Math.floor(hour);
    const minutes = Math.round((hour - wholeHours) * 60);
    date.setHours(wholeHours, minutes, 0, 0);
  }

  function cssLength(value, fallback = "") {
    if (value === false || value === null || value === undefined || value === "") {
      return fallback;
    }
    if (typeof value === "number" && Number.isFinite(value)) return `${value}px`;
    return String(value);
  }

  function normalizeSerial(serial) {
    return String(serial || "").trim().toLowerCase();
  }

  function getRoot(layout) {
    const root = layout && Object.prototype.hasOwnProperty.call(layout, "data")
      ? maybeJson(layout.data)
      : layout;
    return maybeJson(root);
  }

  function getScene(layout) {
    const root = getRoot(layout);
    return root && root.k_100 ? maybeJson(root.k_100) : null;
  }

  function getImageMeta(layout) {
    const root = getRoot(layout);
    return root && root.k_101 ? maybeJson(root.k_101) : null;
  }

  function hasPtd(point, axis) {
    return Number.isFinite(ptdValue(point, axis));
  }

  function ptdValue(point, axis) {
    return Number(point && point.ptd && point.ptd[axis]);
  }

  function panelKey(panel) {
    return String(panel.sn) + ":" + String(panel.prt) + ":" + String(panel.iid);
  }

  function valueMapKeys(panel) {
    const serial = String(panel.sn || "").trim();
    const normalized = normalizeSerial(serial);
    const suffix = serial.slice(-4).toUpperCase();
    const port = String(panel.prt ?? "");
    return [
      panel.key,
      `${normalized}:${port}`,
      `${serial}:${port}`,
      `${suffix}-${port}`,
      `${suffix.toLowerCase()}-${port}`,
      `${suffix}:${port}`,
      `${suffix.toLowerCase()}:${port}`,
    ];
  }

  function normalizedAngle(degrees) {
    let angle = Number(degrees) || 0;
    while (angle > 180) angle -= 360;
    while (angle <= -180) angle += 360;
    return angle;
  }

  function normalizedAxisAngle(degrees) {
    let angle = normalizedAngle(degrees);
    if (angle > 90) angle -= 180;
    if (angle <= -90) angle += 180;
    return angle;
  }

  function vectorAngle(a, b) {
    const dx = ptdValue(b, "x") - ptdValue(a, "x");
    const dz = ptdValue(b, "z") - ptdValue(a, "z");
    if (!Number.isFinite(dx) || !Number.isFinite(dz) || (dx === 0 && dz === 0)) {
      return null;
    }
    return normalizedAxisAngle(Math.atan2(dz, dx) * 180 / Math.PI);
  }

  function vectorDistance(a, b) {
    const dx = ptdValue(b, "x") - ptdValue(a, "x");
    const dz = ptdValue(b, "z") - ptdValue(a, "z");
    return Number.isFinite(dx) && Number.isFinite(dz) ? Math.hypot(dx, dz) : Infinity;
  }

  function centerOf(points) {
    let x = 0;
    let z = 0;
    let count = 0;
    for (const point of points) {
      const px = ptdValue(point, "x");
      const pz = ptdValue(point, "z");
      if (!Number.isFinite(px) || !Number.isFinite(pz)) continue;
      x += px;
      z += pz;
      count += 1;
    }
    return count ? { ptd: { x: x / count, z: z / count } } : null;
  }

  function areaUsesLandscape(place) {
    const direction = place && Number(place.d);
    if (direction === 1) return false;
    if (direction === 2) return true;
    return false;
  }

  function expectedWidthPitch(place) {
    const sx = Number(place && place.sx);
    const sy = Number(place && place.sy);
    if (!Number.isFinite(sx) || sx <= 0 || !Number.isFinite(sy) || sy <= 0) {
      return null;
    }
    const baseWidth = areaUsesLandscape(place) ? Math.max(sx, sy) : Math.min(sx, sy);
    const spacing = Number(place && place.spex);
    return baseWidth + (Number.isFinite(spacing) ? spacing : 0);
  }

  function expectedHeightPitch(place) {
    const sx = Number(place && place.sx);
    const sy = Number(place && place.sy);
    if (!Number.isFinite(sx) || sx <= 0 || !Number.isFinite(sy) || sy <= 0) {
      return null;
    }
    const baseHeight = areaUsesLandscape(place) ? Math.min(sx, sy) : Math.max(sx, sy);
    const spacing = Number(place && place.spey);
    return baseHeight + (Number.isFinite(spacing) ? spacing : 0);
  }

  function scorePitch(distance, expected) {
    if (!Number.isFinite(distance) || distance <= 0) return Infinity;
    if (!Number.isFinite(expected) || expected <= 0) return distance;
    return Math.abs(distance - expected) / expected;
  }

  function median(values) {
    const nums = values.filter((value) => Number.isFinite(value)).sort((a, b) => a - b);
    if (!nums.length) return null;
    const mid = Math.floor(nums.length / 2);
    return nums.length % 2 ? nums[mid] : (nums[mid - 1] + nums[mid]) / 2;
  }

  function bestCandidate(candidates, expected) {
    let best = null;
    for (const candidate of candidates) {
      const score = scorePitch(candidate.distance, expected);
      if (!best || score < best.score || (score === best.score && candidate.distance < best.distance)) {
        best = { ...candidate, score };
      }
    }
    return best;
  }

  function rwAxisCandidate(points, expected) {
    const rwGroups = new Map();
    for (const point of points) {
      if (point.rw == null) continue;
      const key = Number(point.rw);
      if (!rwGroups.has(key)) rwGroups.set(key, []);
      rwGroups.get(key).push(point);
    }
    const keys = Array.from(rwGroups.keys()).sort((a, b) => a - b);
    const candidates = [];
    for (let i = 1; i < keys.length; i += 1) {
      const a = centerOf(rwGroups.get(keys[i - 1]));
      const b = centerOf(rwGroups.get(keys[i]));
      if (!a || !b) continue;
      const angle = vectorAngle(a, b);
      const distance = vectorDistance(a, b);
      if (angle != null && Number.isFinite(distance) && distance > 0) {
        candidates.push({ angle, distance, source: "rw" });
      }
    }
    return bestCandidate(candidates, expected);
  }

  function pairAxisCandidate(points, expected) {
    const candidates = [];
    for (let i = 0; i < points.length; i += 1) {
      for (let j = i + 1; j < points.length; j += 1) {
        const angle = vectorAngle(points[i], points[j]);
        const distance = vectorDistance(points[i], points[j]);
        if (angle != null && Number.isFinite(distance) && distance > 0) {
          candidates.push({ angle, distance, source: "pair" });
        }
      }
    }
    return bestCandidate(candidates, expected);
  }

  function angleInfoFromPtdGrid(points, place) {
    const expected = expectedWidthPitch(place);
    const rw = rwAxisCandidate(points, expected);
    const pair = pairAxisCandidate(points, expected);
    let best = null;
    if (rw && (!pair || rw.score <= pair.score * 1.25 || rw.score <= 0.08)) {
      best = rw;
    } else if (pair) {
      best = pair;
    } else if (rw) {
      best = rw;
    }
    if (best) {
      return {
        angle: best.angle,
        source: best.source,
        distance: best.distance,
        expected,
      };
    }
    return { angle: 0, source: "fallback", distance: null, expected };
  }

  function fittedAxisAngle(points, fallbackAngle) {
    const center = centerOf(points);
    if (!center) return fallbackAngle;

    let xx = 0;
    let zz = 0;
    let xz = 0;
    let count = 0;
    for (const point of points) {
      const x = ptdValue(point, "x");
      const z = ptdValue(point, "z");
      if (!Number.isFinite(x) || !Number.isFinite(z)) continue;
      const dx = x - center.ptd.x;
      const dz = z - center.ptd.z;
      xx += dx * dx;
      zz += dz * dz;
      xz += dx * dz;
      count += 1;
    }
    if (count < 2 || (xx === 0 && zz === 0)) return fallbackAngle;

    let angle = normalizedAxisAngle(0.5 * Math.atan2(2 * xz, xx - zz) * 180 / Math.PI);
    if (Math.abs(normalizedAxisAngle(angle - fallbackAngle)) > 45) {
      angle = normalizedAxisAngle(angle + 90);
    }
    return angle;
  }

  function rowModelsFromPtdGrid(points, angleInfo, place) {
    if (!points || points.length < 2 || !angleInfo || angleInfo.source === "fallback") {
      return [];
    }

    const center = centerOf(points);
    if (!center) return [];

    const angle = normalizedAngle(angleInfo.angle) * Math.PI / 180;
    const ux = Math.cos(angle);
    const uz = Math.sin(angle);
    const vx = -uz;
    const vz = ux;
    const cx = center.ptd.x;
    const cz = center.ptd.z;
    const cy = points.reduce((sum, panel) => sum + (Number(ptdValue(panel, "y")) || 0), 0) / points.length;
    const expectedAlong = expectedWidthPitch(place);
    const expectedCross = expectedHeightPitch(place);
    const tolerance = Number.isFinite(expectedCross) && expectedCross > 0
      ? Math.max(50, expectedCross * 0.35)
      : 500;
    const entries = [];

    for (const panel of points) {
      const px = ptdValue(panel, "x");
      const pz = ptdValue(panel, "z");
      if (!Number.isFinite(px) || !Number.isFinite(pz)) continue;
      const dx = px - cx;
      const dz = pz - cz;
      entries.push({ panel, t: dx * ux + dz * uz, n: dx * vx + dz * vz });
    }

    entries.sort((a, b) => a.n - b.n);
    const rows = [];
    for (const entry of entries) {
      let row = rows[rows.length - 1];
      if (!row || Math.abs(entry.n - row.avgN) > tolerance) {
        row = { entries: [], avgN: entry.n };
        rows.push(row);
      }
      row.entries.push(entry);
      row.avgN = row.entries.reduce((sum, item) => sum + item.n, 0) / row.entries.length;
    }

    const models = [];
    for (const row of rows) {
      row.entries.sort((a, b) => a.t - b.t);
      const diffs = [];
      for (let i = 1; i < row.entries.length; i += 1) {
        const diff = row.entries[i].t - row.entries[i - 1].t;
        if (diff > 0) diffs.push(diff);
      }
      const medianPitch = median(diffs);
      let pitch = Number.isFinite(expectedAlong) && expectedAlong > 0 ? expectedAlong : medianPitch;
      if (
        Number.isFinite(medianPitch)
        && medianPitch > 0
        && (!Number.isFinite(pitch) || pitch <= 0 || Math.abs(medianPitch - pitch) / pitch > 0.35)
      ) {
        pitch = medianPitch;
      }
      const avgT = row.entries.reduce((sum, item) => sum + item.t, 0) / row.entries.length;
      const startT = Number.isFinite(pitch) && pitch > 0
        ? avgT - pitch * (row.entries.length - 1) / 2
        : null;
      const rowEntries = [];
      let minT = Infinity;
      let maxT = -Infinity;
      for (let index = 0; index < row.entries.length; index += 1) {
        const entry = row.entries[index];
        const t = startT == null ? entry.t : startT + pitch * index;
        const x = cx + ux * t + vx * row.avgN;
        const z = cz + uz * t + vz * row.avgN;
        minT = Math.min(minT, t);
        maxT = Math.max(maxT, t);
        rowEntries.push({ panel: entry.panel, t, x, z, index });
      }
      if (rowEntries.length < 2 || !Number.isFinite(minT) || !Number.isFinite(maxT)) {
        continue;
      }
      const centerT = (minT + maxT) / 2;
      models.push({
        angle: angleInfo.angle,
        centerT,
        minT,
        maxT,
        pitch,
        center: {
          x: cx + ux * centerT + vx * row.avgN,
          y: cy,
          z: cz + uz * centerT + vz * row.avgN,
        },
        entries: rowEntries,
      });
    }
    return models;
  }

  class HoymilesLayoutCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._hass = null;
      this._config = {};
      this._state = this._emptyState();
      this._entityIndex = null;
      this._panelElements = new Map();
      this._signalElements = new Map();
      this._metricReferences = { dailyEnergyMax: 0 };
      this._metricMode = "power";
      this._replay = this._emptyReplayState();
      this._historyCache = null;
      this._activePointers = new Map();
      this._dragStart = null;
      this._suppressNextEntityClick = false;
      this._pinchStart = null;
      this._resizeObserver = null;
      this._renderQueued = false;
      this._valueUpdateQueued = false;
    }

    setConfig(config) {
      if (!config || config.layout == null) {
        throw new Error("Hoymiles layout card requires a layout config value.");
      }

      const rssiOkDbm = optionalNumber(
        config.rssi_ok_dbm
          ?? config.rssiOkDbm
          ?? config.inverter_rssi_ok_dbm
          ?? config.inverterRssiOkDbm
          ?? config.inverter_rssi_ok
          ?? config.inverterRssiOk,
        null,
      );
      const rssiBadDbm = optionalNumber(
        config.rssi_bad_dbm
          ?? config.rssiBadDbm
          ?? config.inverter_rssi_bad_dbm
          ?? config.inverterRssiBadDbm
          ?? config.inverter_rssi_bad
          ?? config.inverterRssiBad,
        null,
      );

      this._config = {
        layout: maybeJson(config.layout),
        values: asObject(config.values),
        entities: this._normalizeEntities(config.entities),
        mode: this._normalizeMode(config.mode),
        debugWatts: optionalNumber(config.debug_watts ?? config.debugWatts, null),
        debugDailyEnergy: optionalNumber(
          config.debug_daily_energy ?? config.debugDailyEnergy,
          null,
        ),
        maxWatts: optionalNumber(config.max_watts ?? config.maxWatts, DEFAULT_MAX_WATTS),
        offThresholdWatts: optionalNumber(
          config.off_threshold_watts ?? config.offThresholdWatts,
          DEFAULT_OFF_THRESHOLD_WATTS,
        ),
        aspect: optionalNumber(config.aspect_ratio ?? config.aspectRatio, DEFAULT_ASPECT),
        cropX: optionalNumber(config.crop_x ?? config.cropX, DEFAULT_CROP_X),
        cropY: optionalNumber(config.crop_y ?? config.cropY, DEFAULT_CROP_Y),
        initialZoom: optionalNumber(config.initial_zoom ?? config.initialZoom, 1),
        maxZoom: optionalNumber(config.max_zoom ?? config.maxZoom, DEFAULT_MAX_ZOOM),
        panelTextMinSize: Math.max(0, optionalNumber(
          config.panel_text_min_size
            ?? config.panelTextMinSize
            ?? config.text_min_size
            ?? config.textMinSize,
          30,
        )),
        height: cssLength(config.height ?? config.map_height ?? config.mapHeight ?? config.card_height ?? config.cardHeight),
        minHeight: cssLength(config.min_height ?? config.minHeight, "420px"),
        backgroundUrl: config.background_url ?? config.backgroundUrl ?? "",
        showSerial: config.show_serial !== false && config.showSerial !== false,
        showModeToggle: config.show_mode_toggle !== false && config.showModeToggle !== false,
        showReplayControl: config.show_replay_control !== false
          && config.showReplayControl !== false
          && config.show_replay !== false
          && config.showReplay !== false,
        replayStepSeconds: Math.max(1, optionalNumber(
          config.replay_step_seconds ?? config.replayStepSeconds,
          DEFAULT_REPLAY_STEP_SECONDS,
        )),
        replayStartHour: optionalReplayHour(
          config.replay_start_hour ?? config.replayStartHour,
          DEFAULT_REPLAY_START_HOUR,
        ),
        replayEndHour: optionalReplayHour(
          config.replay_end_hour ?? config.replayEndHour,
          DEFAULT_REPLAY_END_HOUR,
        ),
        replayHours: Math.max(0, optionalNumber(config.replay_hours ?? config.replayHours, 0)),
        signalAnchorPort: Math.max(1, Math.round(optionalNumber(
          config.signal_anchor_port
            ?? config.signalAnchorPort
            ?? config.inverter_near_panel
            ?? config.inverterNearPanel,
          3,
        ))),
        rssiOkDbm,
        rssiBadDbm,
        hasRssiThresholds: rssiOkDbm != null && rssiBadDbm != null && rssiOkDbm > rssiBadDbm,
        historyBatchSize: Math.max(1, Math.round(optionalNumber(
          config.history_batch_size ?? config.historyBatchSize,
          DEFAULT_HISTORY_BATCH_SIZE,
        ))),
      };

      this._state = this._emptyState();
      this._state.viewScale = Math.max(1, this._config.initialZoom);
      this._metricReferences = { dailyEnergyMax: 0 };
      this._metricMode = this._config.mode;
      this._replay = this._emptyReplayState();
      this._historyCache = null;
      this._entityIndex = null;
      this._ensureDom();
      this._loadLayout();
    }

    set hass(hass) {
      const hadHass = Boolean(this._hass);
      this._hass = hass;
      if (!hadHass) this._entityIndex = null;
      if (!this._updatePanelValues()) this._scheduleRender();
    }

    getCardSize() {
      return 9;
    }

    getGridOptions() {
      return {
        columns: "full",
        min_columns: 6,
      };
    }

    connectedCallback() {
      this._ensureDom();
      this._bindResizeObserver();
      this._scheduleRender();
    }

    disconnectedCallback() {
      if (this._resizeObserver) {
        this._resizeObserver.disconnect();
        this._resizeObserver = null;
      }
    }

    _emptyState() {
      return {
        layout: null,
        points: [],
        areaAngles: new Map(),
        areaAngleInfo: new Map(),
        areaRowModels: [],
        areaRowSnaps: new Map(),
        imageWidth: 2000,
        imageHeight: 2940,
        imageScale: 1.53,
        imageMapConvert: 16.2,
        imageMapType: 4,
        imagePosition: { x: 0, y: 0 },
        viewScale: 1,
        offsetX: 0,
        offsetY: 0,
      };
    }

    _emptyReplayState() {
      return {
        enabled: false,
        loading: false,
        error: "",
        startMs: 0,
        endMs: 0,
        selectedMs: 0,
        history: new Map(),
        entityIds: [],
      };
    }

    _ensureDom() {
      if (this.shadowRoot.querySelector(".map")) return;

      this.shadowRoot.innerHTML = `
        <style>${css}</style>
        <ha-card>
          <div class="map" aria-label="Hoymiles solar layout">
            <div class="cameraLayer">
              <img class="background" alt="">
              <div class="overlay"></div>
            </div>
            <div class="modeToggle" aria-label="Panel metric mode">
              <button type="button" data-mode="signal">RSSI</button>
              <button type="button" data-mode="power">W</button>
              <button type="button" data-mode="daily_energy">Wh</button>
            </div>
            <button class="replayButton" type="button" aria-pressed="false">Replay</button>
            <div class="replayScrubber" hidden>
              <button type="button" data-replay-now>Now</button>
              <input class="replayRange" type="range" min="0" max="0" step="${DEFAULT_REPLAY_STEP_SECONDS}" value="0" aria-label="Replay time">
              <span class="replayTime">Live</span>
            </div>
          </div>
        </ha-card>
      `;
      this._map = this.shadowRoot.querySelector(".map");
      this._cameraLayer = this.shadowRoot.querySelector(".cameraLayer");
      this._background = this.shadowRoot.querySelector(".background");
      this._overlay = this.shadowRoot.querySelector(".overlay");
      this._modeToggle = this.shadowRoot.querySelector(".modeToggle");
      this._replayButton = this.shadowRoot.querySelector(".replayButton");
      this._replayScrubber = this.shadowRoot.querySelector(".replayScrubber");
      this._replayRange = this.shadowRoot.querySelector(".replayRange");
      this._replayTime = this.shadowRoot.querySelector(".replayTime");
      this._bindPanZoom();
      this._bindModeToggle();
      this._bindReplayControls();
      this._bindResizeObserver();
    }

    _bindResizeObserver() {
      if (this._resizeObserver || !this._map || !("ResizeObserver" in window)) return;
      this._resizeObserver = new ResizeObserver(() => this._scheduleRender());
      this._resizeObserver.observe(this._map);
    }

    _bindModeToggle() {
      if (!this._modeToggle || this._modeToggle.dataset.bound === "1") return;
      this._modeToggle.dataset.bound = "1";
      this._modeToggle.addEventListener("pointerdown", (event) => event.stopPropagation());
      this._modeToggle.addEventListener("wheel", (event) => event.stopPropagation());
      this._modeToggle.addEventListener("click", (event) => {
        const button = event.target.closest("button[data-mode]");
        if (!button) return;
        event.stopPropagation();
        const nextMode = this._normalizeMode(button.dataset.mode);
        if (nextMode !== "power" && this._replay.enabled) {
          this._disableReplay({ updatePanels: false });
        }
        this._metricMode = nextMode;
        this._updateModeToggle();
        this._updateReplayControls();
        if (!this._updatePanelValues()) this._scheduleRender();
      });
    }

    _updateModeToggle() {
      if (!this._modeToggle) return;
      this._modeToggle.hidden = !this._config.showModeToggle;
      for (const button of this._modeToggle.querySelectorAll("button[data-mode]")) {
        button.classList.toggle("active", this._normalizeMode(button.dataset.mode) === this._metricMode);
      }
    }

    _bindReplayControls() {
      if (!this._replayButton || this._replayButton.dataset.bound === "1") return;
      this._replayButton.dataset.bound = "1";
      const stop = (event) => event.stopPropagation();
      this._replayButton.addEventListener("pointerdown", stop);
      this._replayButton.addEventListener("wheel", stop);
      this._replayButton.addEventListener("click", (event) => {
        event.stopPropagation();
        if (this._replay.enabled) {
          this._disableReplay();
        } else {
          this._enableReplay();
        }
      });

      if (this._replayScrubber) {
        this._replayScrubber.addEventListener("pointerdown", stop);
        this._replayScrubber.addEventListener("wheel", stop);
        this._replayScrubber.addEventListener("click", (event) => event.stopPropagation());
      }

      if (this._replayRange) {
        this._replayRange.addEventListener("input", (event) => {
          event.stopPropagation();
          const stepMs = Math.max(1, this._config.replayStepSeconds || DEFAULT_REPLAY_STEP_SECONDS) * 1000;
          this._setReplaySelected(this._replay.startMs + Number(event.target.value) * stepMs);
        });
      }

      const nowButton = this._replayScrubber && this._replayScrubber.querySelector("[data-replay-now]");
      if (nowButton) {
        nowButton.addEventListener("click", (event) => {
          event.stopPropagation();
          this._disableReplay();
        });
      }
    }

    _updateReplayControls() {
      if (!this._replayButton) return;
      const hidden = !this._config.showReplayControl;
      this._replayButton.hidden = hidden;
      if (hidden) {
        if (this._replayScrubber) this._replayScrubber.hidden = true;
        return;
      }

      const enabled = this._replay.enabled;
      this._replayButton.classList.toggle("active", enabled);
      this._replayButton.setAttribute("aria-pressed", enabled ? "true" : "false");
      this._replayButton.textContent = enabled
        ? (this._replay.loading ? "Loading" : "Live")
        : "Replay";

      if (!this._replayScrubber || !this._replayRange || !this._replayTime) return;
      this._replayScrubber.hidden = !enabled;
      if (!enabled) {
        this._replayTime.textContent = "Live";
        return;
      }

      const stepMs = Math.max(1, this._config.replayStepSeconds || DEFAULT_REPLAY_STEP_SECONDS) * 1000;
      const maxStep = Math.max(0, Math.round((this._replay.endMs - this._replay.startMs) / stepMs));
      const selectedStep = Math.max(
        0,
        Math.min(maxStep, Math.round((this._replay.selectedMs - this._replay.startMs) / stepMs)),
      );
      this._replayRange.min = "0";
      this._replayRange.max = String(maxStep);
      this._replayRange.step = "1";
      this._replayRange.value = String(selectedStep);
      this._replayRange.disabled = this._replay.loading || Boolean(this._replay.error);
      this._replayTime.textContent = this._replay.error
        ? "Unavailable"
        : this._replay.loading
          ? "Loading"
          : this._formatReplayTime(this._replay.selectedMs);
    }

    _formatReplayTime(valueMs) {
      const date = new Date(valueMs || Date.now());
      return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
    }

    _replayRangeForNow() {
      const now = new Date();
      let end;
      let start;
      if (this._config.replayHours > 0) {
        end = now;
        start = new Date(end.getTime() - this._config.replayHours * 60 * 60 * 1000);
      } else {
        start = new Date(now);
        end = new Date(now);
        setDateHour(start, this._config.replayStartHour);
        setDateHour(end, this._config.replayEndHour);
        if (end <= start) end.setDate(end.getDate() + 1);
      }
      const stepMs = Math.max(1, this._config.replayStepSeconds || DEFAULT_REPLAY_STEP_SECONDS) * 1000;
      const startMs = start.getTime();
      const stepCount = Math.max(0, Math.floor((end.getTime() - startMs) / stepMs));
      const endMs = startMs + stepCount * stepMs;
      return { startMs, endMs };
    }

    _setReplaySelected(valueMs) {
      if (!this._replay.enabled) return;
      const stepMs = Math.max(1, this._config.replayStepSeconds || DEFAULT_REPLAY_STEP_SECONDS) * 1000;
      const rawMs = Number(valueMs) || this._replay.endMs;
      const stepIndex = Math.round((rawMs - this._replay.startMs) / stepMs);
      const snappedMs = this._replay.startMs + stepIndex * stepMs;
      const selectedMs = Math.max(
        this._replay.startMs,
        Math.min(this._replay.endMs, snappedMs),
      );
      this._replay.selectedMs = selectedMs;
      this._updateReplayControls();
      this._schedulePanelValueUpdate();
    }

    _disableReplay(options = {}) {
      const updatePanels = options.updatePanels !== false;
      this._replay.enabled = false;
      this._replay.loading = false;
      this._replay.error = "";
      this._replay.selectedMs = 0;
      this._updateReplayControls();
      if (updatePanels) this._schedulePanelValueUpdate();
    }

    async _enableReplay() {
      if (!this._config.showReplayControl) return;
      if (!this._hass || typeof this._hass.callWS !== "function") {
        this._replay = {
          ...this._emptyReplayState(),
          enabled: true,
          error: "Home Assistant history API is unavailable",
        };
        this._updateReplayControls();
        this._schedulePanelValueUpdate();
        return;
      }

      const range = this._replayRangeForNow();
      this._metricMode = "power";
      this._replay = {
        ...this._emptyReplayState(),
        enabled: true,
        loading: true,
        startMs: range.startMs,
        endMs: range.endMs,
        selectedMs: range.endMs,
      };
      this._updateModeToggle();
      this._updateReplayControls();
      this._schedulePanelValueUpdate();

      const requestId = (this._replayRequestId || 0) + 1;
      this._replayRequestId = requestId;
      try {
        const history = await this._loadReplayHistory(range);
        if (this._replayRequestId !== requestId || !this._replay.enabled) return;
        this._replay = {
          ...this._replay,
          loading: false,
          error: "",
          history: history.history,
          entityIds: history.entityIds,
          startMs: history.startMs,
          endMs: history.endMs,
          selectedMs: Math.min(this._replay.selectedMs || history.endMs, history.endMs),
        };
      } catch (error) {
        if (this._replayRequestId !== requestId || !this._replay.enabled) return;
        this._replay = {
          ...this._replay,
          loading: false,
          error: error && error.message ? error.message : "Could not load history",
          history: new Map(),
        };
      }
      this._updateReplayControls();
      this._schedulePanelValueUpdate();
    }

    _powerEntityIds() {
      const ids = new Set();
      for (const panel of this._state.points) {
        const entityId = this._entityForPanel(panel, "power");
        if (entityId) ids.add(entityId);
      }
      return Array.from(ids).sort();
    }

    _historyCacheKey(entityIds, range) {
      const step = this._config.replayStepSeconds || DEFAULT_REPLAY_STEP_SECONDS;
      return `${range.startMs}-${range.endMs}-${step}|${entityIds.join("|")}`;
    }

    async _loadReplayHistory(range) {
      const entityIds = this._powerEntityIds();
      if (!entityIds.length) throw new Error("No power entities found");

      const cacheKey = this._historyCacheKey(entityIds, range);
      if (
        this._historyCache
        && this._historyCache.key === cacheKey
        && Date.now() - this._historyCache.fetchedAt < REPLAY_CACHE_TTL_MS
      ) {
        return this._historyCache;
      }

      const history = new Map();
      for (let i = 0; i < entityIds.length; i += this._config.historyBatchSize) {
        const batch = entityIds.slice(i, i + this._config.historyBatchSize);
        const result = await this._hass.callWS({
          type: "history/history_during_period",
          start_time: new Date(range.startMs).toISOString(),
          end_time: new Date(range.endMs).toISOString(),
          entity_ids: batch,
          minimal_response: true,
          no_attributes: true,
        });
        this._mergeHistoryResult(history, result);
      }

      for (const values of history.values()) {
        values.sort((a, b) => a.ts - b.ts);
      }
      const sampledHistory = this._sampleHistoryValues(history, range);

      this._historyCache = {
        key: cacheKey,
        fetchedAt: Date.now(),
        startMs: range.startMs,
        endMs: range.endMs,
        entityIds,
        history: sampledHistory,
      };
      return this._historyCache;
    }

    _sampleHistoryValues(history, range) {
      const sampled = new Map();
      const stepMs = Math.max(1, this._config.replayStepSeconds || DEFAULT_REPLAY_STEP_SECONDS) * 1000;
      for (const [entityId, states] of history.entries()) {
        if (!states.length) continue;
        const values = [];
        let index = 0;
        let current = null;
        for (let ts = range.startMs; ts <= range.endMs; ts += stepMs) {
          while (index < states.length && states[index].ts <= ts) {
            current = states[index].value;
            index += 1;
          }
          if (current != null) values.push({ ts, value: current });
        }
        sampled.set(entityId, values);
      }
      return sampled;
    }

    _mergeHistoryResult(target, result) {
      if (!result) return;
      if (Array.isArray(result)) {
        for (const group of result) {
          if (!Array.isArray(group) || !group.length) continue;
          const entityId = group[0].entity_id || group[0].e;
          if (entityId) this._appendHistoryStates(target, entityId, group);
        }
        return;
      }

      if (typeof result === "object") {
        for (const [entityId, states] of Object.entries(result)) {
          if (Array.isArray(states)) this._appendHistoryStates(target, entityId, states);
        }
      }
    }

    _appendHistoryStates(target, entityId, states) {
      if (!target.has(entityId)) target.set(entityId, []);
      const values = target.get(entityId);
      for (const state of states) {
        const value = numericValue(state && (state.s ?? state.state));
        const ts = this._historyTimestamp(state);
        if (value != null && Number.isFinite(ts)) values.push({ ts, value });
      }
    }

    _historyTimestamp(state) {
      if (!state) return null;
      const numeric = state.lu ?? state.lc ?? state.last_updated_ts ?? state.last_changed_ts;
      if (Number.isFinite(Number(numeric))) {
        const ts = Number(numeric);
        return ts > 100000000000 ? ts : ts * 1000;
      }
      const text = state.last_updated || state.last_changed;
      if (!text) return null;
      const parsed = Date.parse(text);
      return Number.isFinite(parsed) ? parsed : null;
    }

    _historyValueAt(entityId, selectedMs) {
      const states = this._replay.history.get(entityId);
      if (!states || !states.length) return null;
      let low = 0;
      let high = states.length - 1;
      let match = -1;
      while (low <= high) {
        const mid = Math.floor((low + high) / 2);
        if (states[mid].ts <= selectedMs) {
          match = mid;
          low = mid + 1;
        } else {
          high = mid - 1;
        }
      }
      return match >= 0 ? states[match].value : null;
    }

    _schedulePanelValueUpdate() {
      if (this._valueUpdateQueued) return;
      this._valueUpdateQueued = true;
      window.requestAnimationFrame(() => {
        this._valueUpdateQueued = false;
        if (!this._updatePanelValues()) this._scheduleRender();
      });
    }

    _normalizeMode(mode) {
      const value = String(mode || "power").toLowerCase();
      if (value === "daily" || value === "daily_energy" || value === "energy" || value === "wh") {
        return "daily_energy";
      }
      if (
        value === "signal"
        || value === "rssi"
        || value === "signal_strength"
        || value === "signal-strength"
      ) {
        return "signal";
      }
      return "power";
    }

    _normalizeEntityMap(value) {
      const result = new Map();
      const parsed = maybeJson(value);
      if (!parsed || typeof parsed !== "object") return result;

      for (const [key, entityId] of Object.entries(parsed)) {
        if (typeof entityId === "string") result.set(String(key).toLowerCase(), entityId);
      }
      return result;
    }

    _normalizeEntities(entities) {
      const parsed = maybeJson(entities);
      const result = {
        power: new Map(),
        dailyEnergy: new Map(),
        signalStrength: new Map(),
      };
      if (Array.isArray(parsed)) {
        for (const entry of parsed) {
          if (!entry || !entry.entity) continue;
          const serial = String(entry.serial ?? entry.sn ?? "").trim();
          const port = String(entry.port ?? entry.prt ?? "").trim();
          const metric = this._normalizeMode(entry.metric ?? entry.mode);
          const target = metric === "daily_energy"
            ? result.dailyEnergy
            : metric === "signal"
              ? result.signalStrength
              : result.power;
          if (serial && metric === "signal") {
            this._addSerialEntityKeys(target, serial, entry.entity);
          } else if (serial && port) {
            this._addEntityKeys(target, serial, port, entry.entity);
          }
          if (entry.key) target.set(String(entry.key).toLowerCase(), entry.entity);
        }
        return result;
      }

      if (parsed && typeof parsed === "object") {
        if (
          parsed.power
          || parsed.daily_energy
          || parsed.dailyEnergy
          || parsed.signal_strength
          || parsed.signalStrength
          || parsed.signal
          || parsed.rssi
        ) {
          result.power = this._normalizeEntityMap(parsed.power);
          result.dailyEnergy = this._normalizeEntityMap(parsed.daily_energy ?? parsed.dailyEnergy);
          result.signalStrength = this._normalizeEntityMap(
            parsed.signal_strength ?? parsed.signalStrength ?? parsed.signal ?? parsed.rssi,
          );
        } else {
          for (const [key, entityId] of Object.entries(parsed)) {
            if (typeof entityId === "string") result.power.set(String(key).toLowerCase(), entityId);
          }
        }
      }
      return result;
    }

    _loadLayout() {
      try {
        const layout = typeof this._config.layout === "string"
          ? JSON.parse(this._config.layout)
          : this._config.layout;
        const image = getImageMeta(layout);
        this._state.layout = layout;
        this._state.imageWidth = Number(image && image.mw) || 2000;
        this._state.imageHeight = Number(image && image.mh) || 2940;
        this._state.imageMapType = Number(image && (image.mt ?? image.mapType)) || 4;
        this._state.imageScale = Number(
          image && (
            this._state.imageMapType === 4
              ? (image.ms ?? image.customScale)
              : (image.s ?? image.scale)
          ),
        ) || 1.53;
        this._state.imageMapConvert = Number(image && image.mcvt) || 16.2;
        this._state.imagePosition = {
          x: Number(image && image.p && image.p.x) || 0,
          y: Number(image && image.p && image.p.y) || 0,
        };
        this._state.points = this._extractPanels(layout);
        this._rebuildRows();
        this._background.src = this._config.backgroundUrl || (image && image.mu) || "";
        this.style.setProperty("--hoymiles-map-aspect", String(this._config.aspect || DEFAULT_ASPECT));
        this.style.setProperty("--hoymiles-map-min-height", this._config.minHeight);
        if (this._config.height) {
          this.style.setProperty("--hoymiles-map-height", this._config.height);
        } else {
          this.style.removeProperty("--hoymiles-map-height");
        }
        this._updateModeToggle();
        this._updateReplayControls();
        this._clearError();
        this._scheduleRender();
      } catch (error) {
        this._showError(`Could not render Hoymiles map: ${error.message}`);
      }
    }

    _areaInfoMap(layout) {
      const map = new Map();
      const scene = getScene(layout);
      if (!scene || !Array.isArray(scene.pls)) return map;
      for (const place of scene.pls) {
        const info = { name: place.n || `Area ${place.iid}`, place };
        if (place.iid != null) map.set(String(place.iid), info);
        if (place.xid != null) map.set(String(place.xid), info);
      }
      return map;
    }

    _extractPanels(layout) {
      const scene = getScene(layout);
      if (!scene || !Array.isArray(scene.emts)) return [];
      const areas = this._areaInfoMap(layout);
      return scene.emts
        .filter((panel) => panel && panel.ptd && hasPtd(panel, "x") && hasPtd(panel, "z"))
        .map((panel, index) => {
          const info = areas.get(String(panel.lid)) || {};
          return {
            ...panel,
            index,
            area: info.name || `Area ${panel.lid}`,
            areaPlace: info.place || null,
            key: panelKey(panel),
          };
        });
    }

    _rebuildRows() {
      this._state.areaAngles = new Map();
      this._state.areaAngleInfo = new Map();
      this._state.areaRowModels = [];
      this._state.areaRowSnaps = new Map();
      const byArea = new Map();

      for (const panel of this._state.points) {
        const areaKey = String(panel.lid || panel.area || "");
        if (!byArea.has(areaKey)) byArea.set(areaKey, []);
        byArea.get(areaKey).push(panel);
      }

      for (const [areaKey, panels] of byArea.entries()) {
        const first = panels[0] || {};
        const info = angleInfoFromPtdGrid(panels, first.areaPlace);
        const fittedAngle = info.source === "fallback"
          ? info.angle
          : fittedAxisAngle(panels, info.angle);
        const renderInfo = { ...info, angle: fittedAngle };
        this._state.areaAngles.set(areaKey, renderInfo.angle);
        this._state.areaAngleInfo.set(areaKey, renderInfo);
        const rows = rowModelsFromPtdGrid(panels, renderInfo, first.areaPlace);
        for (const row of rows) {
          this._state.areaRowModels.push({ ...row, areaKey });
          for (const entry of row.entries) {
            this._state.areaRowSnaps.set(entry.panel.key, { x: entry.x, z: entry.z });
          }
        }
      }
    }

    _scheduleRender() {
      if (this._renderQueued || !this._overlay) return;
      this._renderQueued = true;
      window.requestAnimationFrame(() => {
        this._renderQueued = false;
        this._render();
      });
    }

    _effectivePtdScale() {
      const scale = Number(this._state.imageScale);
      const mapConvert = Number(this._state.imageMapConvert);
      return Number.isFinite(scale) && scale > 0 && Number.isFinite(mapConvert) && mapConvert > 0
        ? mapConvert / (1000 * scale)
        : 0.010588;
    }

    _absoluteMapOrigin(scale) {
      return {
        x: this._state.imageWidth / 2 - Number(this._state.imagePosition.x || 0) * scale,
        y: this._state.imageHeight / 2 - Number(this._state.imagePosition.y || 0) * scale,
      };
    }

    _projectPtd(ptd) {
      const scale = this._effectivePtdScale();
      const origin = this._absoluteMapOrigin(scale);
      return {
        x: origin.x + Number(ptd.x || 0) * scale,
        y: origin.y + Number(ptd.z || 0) * scale,
      };
    }

    _stagePercentFor(pos) {
      return {
        left: pos.x / this._state.imageWidth * 100,
        top: pos.y / this._state.imageHeight * 100,
      };
    }

    _cameraLayerLayout() {
      const imageAspect = this._state.imageWidth / this._state.imageHeight;
      const rect = this._map.getBoundingClientRect();
      const cardAspect = rect.width > 0 && rect.height > 0
        ? rect.width / rect.height
        : this._config.aspect || DEFAULT_ASPECT;
      if (cardAspect > imageAspect) {
        const height = cardAspect / imageAspect * 100;
        return { left: 0, top: (100 - height) * this._config.cropY, width: 100, height };
      }
      const width = imageAspect / cardAspect * 100;
      return { left: (100 - width) * this._config.cropX, top: 0, width, height: 100 };
    }

    _cameraLayerPixelLayout() {
      const rect = this._map.getBoundingClientRect();
      const layout = this._cameraLayerLayout();
      return {
        left: rect.width * layout.left / 100,
        top: rect.height * layout.top / 100,
        width: rect.width * layout.width / 100,
        height: rect.height * layout.height / 100,
      };
    }

    _applyCameraLayerLayout() {
      const layout = this._cameraLayerPixelLayout();
      this._cameraLayer.style.left = `${layout.left}px`;
      this._cameraLayer.style.top = `${layout.top}px`;
      this._cameraLayer.style.width = `${layout.width}px`;
      this._cameraLayer.style.height = `${layout.height}px`;
    }

    _coverFitScaleCss() {
      const layer = this._cameraLayerPixelLayout();
      if (!layer.width || !layer.height) return { x: 1, y: 1 };
      return {
        x: layer.width / this._state.imageWidth,
        y: layer.height / this._state.imageHeight,
      };
    }

    _stageSizeForNative(width, height) {
      return {
        width: `${width / this._state.imageWidth * 100}%`,
        height: `${height / this._state.imageHeight * 100}%`,
      };
    }

    _clampCamera() {
      const stageRect = this._map.getBoundingClientRect();
      if (!stageRect.width || !stageRect.height) return;
      const layer = this._cameraLayerPixelLayout();
      const scaledW = layer.width * this._state.viewScale;
      const scaledH = layer.height * this._state.viewScale;
      const fit = this._coverFitScaleCss();

      const clampAxis = (offsetCss, layerStart, layerSize, scaledSize, viewportSize) => {
        if (scaledSize <= viewportSize) return viewportSize / 2 - (layerStart + layerSize / 2);
        const baseStart = layerStart + (layerSize - scaledSize) / 2;
        const minOffset = viewportSize - (baseStart + scaledSize);
        const maxOffset = -baseStart;
        return Math.min(maxOffset, Math.max(minOffset, offsetCss));
      };

      const offsetCssX = this._state.offsetX * fit.x * this._state.viewScale;
      const offsetCssY = this._state.offsetY * fit.y * this._state.viewScale;
      this._state.offsetX = fit.x
        ? clampAxis(offsetCssX, layer.left, layer.width, scaledW, stageRect.width) / (fit.x * this._state.viewScale)
        : this._state.offsetX;
      this._state.offsetY = fit.y
        ? clampAxis(offsetCssY, layer.top, layer.height, scaledH, stageRect.height) / (fit.y * this._state.viewScale)
        : this._state.offsetY;
    }

    _applyCamera() {
      this._clampCamera();
      const layer = this._cameraLayerPixelLayout();
      const fit = this._coverFitScaleCss();
      const scaledWidth = layer.width * this._state.viewScale;
      const scaledHeight = layer.height * this._state.viewScale;
      const offsetX = this._state.offsetX * fit.x * this._state.viewScale;
      const offsetY = this._state.offsetY * fit.y * this._state.viewScale;
      this._cameraLayer.style.left = `${layer.left + layer.width / 2 - scaledWidth / 2 + offsetX}px`;
      this._cameraLayer.style.top = `${layer.top + layer.height / 2 - scaledHeight / 2 + offsetY}px`;
      this._cameraLayer.style.width = `${scaledWidth}px`;
      this._cameraLayer.style.height = `${scaledHeight}px`;
      this._cameraLayer.style.transform = "translateZ(0)";
    }

    _hoymilesCellSize(place) {
      const scale = this._effectivePtdScale();
      const sx = Number(place && place.sx);
      const sy = Number(place && place.sy);
      const landscape = areaUsesLandscape(place);
      const hasJsonSize = Number.isFinite(sx) && sx > 0 && Number.isFinite(sy) && sy > 0;
      return {
        width: hasJsonSize ? (landscape ? Math.max(sx, sy) : Math.min(sx, sy)) * scale : 12,
        height: hasJsonSize ? (landscape ? Math.min(sx, sy) : Math.max(sx, sy)) * scale : 18,
      };
    }

    _panelAngleFor(panel) {
      return normalizedAxisAngle(this._state.areaAngles.get(String(panel.lid || panel.area || "")) || 0);
    }

    _panelTextRotation(layout) {
      let rotation = layout.height >= layout.width ? 90 : 0;
      const screenAngle = normalizedAngle(layout.angle + rotation);
      if (screenAngle > 90 || screenAngle <= -90) rotation += 180;
      return normalizedAngle(rotation);
    }

    _panelFontSize(displaySize, text = "") {
      const shortSide = Math.max(1, Math.min(Number(displaySize.width) || 1, Number(displaySize.height) || 1));
      const longSide = Math.max(1, Math.max(Number(displaySize.width) || 1, Number(displaySize.height) || 1));
      const baseSize = shortSide * 0.36;
      if (!text) return Math.max(7, baseSize);

      const estimatedTextWidth = Math.max(1, text.length) * 0.55;
      const fitSize = longSide * 0.72 / estimatedTextWidth;
      return Math.max(7, Math.min(baseSize, fitSize));
    }

    _panelIdFontSize(displaySize) {
      const shortSide = Math.max(1, Math.min(Number(displaySize.width) || 1, Number(displaySize.height) || 1));
      return Math.max(5, shortSide * 0.1);
    }

    _panelDisplaySize(layout) {
      const fit = this._coverFitScaleCss();
      return {
        width: layout.width * fit.x * this._state.viewScale,
        height: layout.height * fit.y * this._state.viewScale,
      };
    }

    _signalFontSize(panel) {
      const cell = this._hoymilesCellSize(panel.areaPlace || {});
      const displaySize = this._panelDisplaySize(cell);
      const shortSide = Math.max(1, Math.min(displaySize.width, displaySize.height));
      return Math.max(10, Math.min(30, shortSide * 0.32));
    }

    _addEntityKeys(target, serial, port, entityId) {
      const normalized = normalizeSerial(serial);
      const suffix = String(serial || "").slice(-4).toLowerCase();
      const portText = String(port);
      target.set(`${normalized}:${portText}`, entityId);
      target.set(`${suffix}-${portText}`, entityId);
      target.set(`${suffix}:${portText}`, entityId);
    }

    _addSerialEntityKeys(target, serial, entityId) {
      const normalized = normalizeSerial(serial);
      const suffix = String(serial || "").slice(-4).toLowerCase();
      if (normalized) target.set(normalized, entityId);
      if (suffix) target.set(suffix, entityId);
    }

    _entityMapForMetric(metric) {
      if (metric === "daily_energy") return this._config.entities.dailyEnergy;
      if (metric === "signal") return this._config.entities.signalStrength;
      return this._config.entities.power;
    }

    _indexMapForMetric(index, metric) {
      if (metric === "daily_energy") return index.dailyEnergy;
      if (metric === "signal") return index.signalStrength;
      return index.power;
    }

    _directEntityIds(panel, metric) {
      const serial = normalizeSerial(panel.sn);
      const port = String(panel.prt ?? "");
      if (!serial || !port) return [];
      return metric === "daily_energy"
        ? [`sensor.inverter_${serial}_port_${port}_dc_daily_energy`]
        : [`sensor.inverter_${serial}_port_${port}_dc_power`];
    }

    _directSignalEntityIds(serial) {
      const normalized = normalizeSerial(serial);
      return normalized ? [`sensor.inverter_${normalized}_signal_strength`] : [];
    }

    _signalEntityForSerial(serial) {
      const explicitMap = this._entityMapForMetric("signal");
      const normalized = normalizeSerial(serial);
      const suffix = String(serial || "").slice(-4).toLowerCase();
      for (const key of [normalized, suffix]) {
        const explicit = explicitMap.get(key);
        if (explicit) return explicit;
      }

      const states = this._hass && this._hass.states ? this._hass.states : {};
      for (const entityId of this._directSignalEntityIds(serial)) {
        if (states[entityId]) return entityId;
      }

      const index = this._buildEntityIndex();
      const signalIndex = this._indexMapForMetric(index, "signal");
      for (const key of [normalized, suffix]) {
        const entityId = signalIndex.get(key);
        if (entityId) return entityId;
      }
      return null;
    }

    _entityForPanel(panel, metric = "power") {
      const explicitMap = this._entityMapForMetric(metric);
      for (const key of valueMapKeys(panel)) {
        const explicit = explicitMap.get(String(key).toLowerCase());
        if (explicit) return explicit;
      }

      const states = this._hass && this._hass.states ? this._hass.states : {};
      for (const entityId of this._directEntityIds(panel, metric)) {
        if (states[entityId]) return entityId;
      }

      const index = this._buildEntityIndex();
      const metricIndex = this._indexMapForMetric(index, metric);
      for (const key of valueMapKeys(panel)) {
        const entityId = metricIndex.get(String(key).toLowerCase());
        if (entityId) return entityId;
      }
      return null;
    }

    _buildEntityIndex() {
      if (this._entityIndex) return this._entityIndex;

      const index = {
        power: new Map(),
        dailyEnergy: new Map(),
        signalStrength: new Map(),
      };
      const states = this._hass && this._hass.states ? this._hass.states : {};
      for (const [entityId, stateObj] of Object.entries(states)) {
        if (!entityId.startsWith("sensor.") || !stateObj || !stateObj.attributes) continue;
        const attrs = stateObj.attributes;
        const metric = this._metricFromEntity(entityId, attrs);
        if (!metric) continue;

        const serial = this._serialFromEntity(entityId, stateObj, attrs);
        if (!serial) continue;

        if (metric === "signal") {
          this._addSerialEntityKeys(this._indexMapForMetric(index, metric), serial, entityId);
          continue;
        }

        const port = this._portFromEntity(entityId, attrs);
        if (!port) continue;
        this._addEntityKeys(this._indexMapForMetric(index, metric), serial, port, entityId);
      }

      this._entityIndex = index;
      return index;
    }

    _metricFromEntity(entityId, attrs) {
      const name = `${entityId} ${attrs.friendly_name || ""}`.toLowerCase();
      const unit = String(attrs.unit_of_measurement || "").toLowerCase();
      if (
        name.includes("signal_strength")
        || name.includes("signal strength")
        || name.includes("rssi")
        || attrs.device_class === "signal_strength"
        || unit === "dbm"
      ) {
        return "signal";
      }

      const isPort = attrs.port_number != null || name.includes("port");
      const isDc = name.includes("dc") || attrs.inverter_serial_number;
      if (!isPort || !isDc) return null;

      if (
        name.includes("dc_daily_energy")
        || name.includes("daily energy")
        || (attrs.device_class === "energy" && (unit === "wh" || unit === "kwh"))
      ) {
        return "daily_energy";
      }

      if (
        name.includes("dc_power")
        || name.includes("dc power")
        || (attrs.device_class === "power" && unit === "w")
      ) {
        return "power";
      }

      return null;
    }

    _portFromEntity(entityId, attrs) {
      if (attrs.port_number != null) return String(attrs.port_number);
      const text = `${entityId} ${attrs.friendly_name || ""}`;
      const match = text.match(/port[_\s-]*(\d+)/i);
      return match ? match[1] : "";
    }

    _serialFromEntity(entityId, stateObj, attrs) {
      if (attrs.inverter_serial_number) return String(attrs.inverter_serial_number);

      const entityRegistry = this._hass && this._hass.entities ? this._hass.entities[entityId] : null;
      const deviceId = entityRegistry && entityRegistry.device_id;
      const device = deviceId && this._hass && this._hass.devices ? this._hass.devices[deviceId] : null;
      if (device && device.serial_number) return String(device.serial_number);

      const sourceText = [
        attrs.friendly_name,
        entityId,
        stateObj && stateObj.name,
        device && (device.name_by_user || device.name),
      ].filter(Boolean).join(" ");
      const match = sourceText.match(/\b(?=[a-z0-9]*\d)[a-z0-9]{10,16}\b/i);
      return match ? match[0] : "";
    }

    _entityMetric(panel, metric) {
      const entityId = this._entityForPanel(panel, metric);
      if (!entityId || !this._hass || !this._hass.states || !this._hass.states[entityId]) {
        return { value: null, synthetic: false, entityId: null, unit: metric === "daily_energy" ? "Wh" : "W" };
      }

      const stateObj = this._hass.states[entityId];
      const value = numericValue(stateObj.state);
      return {
        value,
        synthetic: false,
        entityId,
        unit: stateObj.attributes && stateObj.attributes.unit_of_measurement
          ? stateObj.attributes.unit_of_measurement
          : metric === "daily_energy" ? "Wh" : "W",
      };
    }

    _configuredMetric(panel, metric) {
      for (const key of valueMapKeys(panel)) {
        const source = this._config.values[metric] ?? this._config.values;
        const value = source && typeof source === "object"
          ? numericValue(source[key] ?? source[String(key).toLowerCase()])
          : null;
        if (value != null) {
          return {
            value,
            synthetic: false,
            entityId: null,
            unit: metric === "daily_energy" ? "Wh" : "W",
          };
        }
      }
      return null;
    }

    _mappedMetric(panel, metric) {
      const configured = this._configuredMetric(panel, metric);
      if (configured) return configured;

      const entityMetric = this._entityMetric(panel, metric);
      if (entityMetric.entityId || entityMetric.value != null) return entityMetric;

      if (metric === "power" && this._config.debugWatts != null) {
        return { value: this._config.debugWatts, synthetic: true, entityId: null, unit: "W" };
      }
      if (metric === "daily_energy" && this._config.debugDailyEnergy != null) {
        return { value: this._config.debugDailyEnergy, synthetic: true, entityId: null, unit: "Wh" };
      }
      return { value: null, synthetic: false, entityId: null, unit: metric === "daily_energy" ? "Wh" : "W" };
    }

    _replayPowerMetric(panel) {
      const entityId = this._entityForPanel(panel, "power");
      if (!entityId || this._replay.loading || this._replay.error) {
        return { value: null, synthetic: false, entityId, unit: "W", historical: true };
      }
      return {
        value: this._historyValueAt(entityId, this._replay.selectedMs),
        synthetic: false,
        entityId,
        unit: "W",
        historical: true,
      };
    }

    _signalMetric(serial) {
      const entityId = this._signalEntityForSerial(serial);
      if (!entityId || !this._hass || !this._hass.states || !this._hass.states[entityId]) {
        return { value: null, synthetic: false, entityId, unit: "dBm" };
      }

      const stateObj = this._hass.states[entityId];
      return {
        value: numericValue(stateObj.state),
        synthetic: false,
        entityId,
        unit: stateObj.attributes && stateObj.attributes.unit_of_measurement
          ? stateObj.attributes.unit_of_measurement
          : "dBm",
      };
    }

    _panelMetrics(panel) {
      const power = this._replay.enabled && this._metricMode === "power"
        ? this._replayPowerMetric(panel)
        : this._mappedMetric(panel, "power");
      const dailyEnergy = this._mappedMetric(panel, "daily_energy");
      const display = this._metricMode === "daily_energy"
        ? dailyEnergy
        : power;
      return { power, dailyEnergy, display };
    }

    _formatMetric(metric) {
      if (!metric || metric.value == null || !Number.isFinite(Number(metric.value))) return "";
      const unit = metric.unit || "W";
      return `${Math.round(Number(metric.value))} ${unit}`;
    }

    _formatSignalMetric(metric) {
      if (!metric || this._isMissingSignalValue(metric.value)) return "-- dBm";
      return `${Math.round(Number(metric.value))} ${metric.unit || "dBm"}`;
    }

    _isMissingSignalValue(value) {
      if (value == null || !Number.isFinite(Number(value))) return true;
      return Number(value) >= 0;
    }

    _fillValue(metric, mode) {
      if (!metric || metric.value == null || !Number.isFinite(Number(metric.value))) return null;
      const value = Number(metric.value);
      if (mode === "daily_energy" && String(metric.unit || "").toLowerCase() === "kwh") {
        return value * 1000;
      }
      return value;
    }

    _formatWatts(value) {
      if (value == null || !Number.isFinite(Number(value))) return "";
      return `${Math.round(Number(value))} W`;
    }

    _inverterPortLabel(panel) {
      const serial = String(panel && panel.sn != null ? panel.sn : "").trim().toUpperCase();
      return `${serial ? serial.slice(-4) : "----"}-${String(panel && panel.prt != null ? panel.prt : "")}`;
    }

    _appendPanelText(item, panel, metric, layout, displaySize) {
      const screenShortSide = Math.min(displaySize.width, displaySize.height);
      const screenLongSide = Math.max(displaySize.width, displaySize.height);
      const minShortSide = Math.max(0, this._config.panelTextMinSize || 0);
      const minLongSide = minShortSide * 46 / 30;
      if (screenShortSide < minShortSide || screenLongSide < minLongSide) return;

      const hasMetric = metric.value != null;
      const hasId = this._config.showSerial;
      if (!hasMetric && !hasId) return;

      const metricText = hasMetric ? this._formatMetric(metric) : "";
      item.style.setProperty("--panel-font", `${this._panelFontSize(displaySize, metricText).toFixed(2)}px`);
      item.style.setProperty("--panel-id-font", `${this._panelIdFontSize(displaySize).toFixed(2)}px`);
      item.style.setProperty("--metric-rotation", `${this._panelTextRotation(layout).toFixed(2)}deg`);

      const stack = document.createElement("span");
      stack.className = "panelTextStack";
      if (hasMetric) {
        const metricEl = document.createElement("span");
        metricEl.className = "panelMetric";
        const value = document.createElement("span");
        value.className = "value";
        value.textContent = metricText;
        metricEl.appendChild(value);
        stack.appendChild(metricEl);
      }

      if (hasId) {
        const id = document.createElement("span");
        id.className = "panelId";
        id.textContent = this._inverterPortLabel(panel);
        stack.appendChild(id);
      }

      item.appendChild(stack);
    }

    _applyPanelChrome(item, metrics, layout, displaySize) {
      const screenShortSide = Math.max(1, Math.min(displaySize.width, displaySize.height));
      const frame = screenShortSide < 80 ? 0.18 : 0.24;
      const radius = screenShortSide < 140 ? 0.25 : 0.55;
      const metric = this._metricMode === "daily_energy" ? metrics.dailyEnergy : metrics.power;
      const value = this._fillValue(metric, this._metricMode);
      const reference = this._metricMode === "daily_energy"
        ? this._metricReferences.dailyEnergyMax
        : this._config.maxWatts;
      const isOff = value == null || !Number.isFinite(value) || value < this._config.offThresholdWatts;
      const fill = isOff || !Number.isFinite(reference) || reference <= 0
        ? 0
        : Math.max(0, Math.min(100, value / reference * 100));
      item.style.setProperty("--panel-frame", `${frame.toFixed(2)}%`);
      item.style.setProperty("--panel-radius", `${radius.toFixed(2)}%`);
      item.style.setProperty("--panel-fill", `${fill.toFixed(1)}%`);
      item.style.setProperty("--panel-fill-angle", layout.height >= layout.width ? "90deg" : "0deg");
      item.classList.toggle("off", isOff);

      const fillElement = document.createElement("span");
      fillElement.className = layout.height >= layout.width ? "panelFill vertical" : "panelFill";
      item.appendChild(fillElement);
    }

    _configurePanelItem(item, panel, layout) {
      const metrics = this._panelMetrics(panel);
      const displaySize = this._panelDisplaySize(layout);
      item.innerHTML = "";
      this._applyPanelChrome(item, metrics, layout, displaySize);
      this._appendPanelText(item, panel, metrics.display, layout, displaySize);
      item.title = [
        panel.area,
        `SN ${panel.sn}`,
        `Port ${panel.prt}`,
        this._replay.enabled && this._metricMode === "power"
          ? (this._replay.error || `Replay ${this._formatReplayTime(this._replay.selectedMs)}`)
          : "",
        metrics.power.value == null ? "No power entity/value" : this._formatMetric(metrics.power),
        this._metricMode === "daily_energy" && metrics.display.value != null
          ? this._formatMetric(metrics.display)
          : "",
        this._metricMode === "daily_energy" && this._metricReferences.dailyEnergyMax > 0
          ? `Wh reference ${Math.round(this._metricReferences.dailyEnergyMax)} Wh`
          : "",
      ].filter(Boolean).join("\n");
      const moreInfoEntityId = metrics.display.entityId || metrics.power.entityId;
      if (moreInfoEntityId) {
        item.dataset.entityId = moreInfoEntityId;
        item.onclick = (event) => {
          this._openMoreInfoFromClick(event, moreInfoEntityId);
        };
      } else {
        delete item.dataset.entityId;
        item.onclick = null;
      }
    }

    _createPanelItem(panel, layout) {
      const item = document.createElement("div");
      item.className = "panelItem";
      this._configurePanelItem(item, panel, layout);
      this._panelElements.set(panel.key, { item, panel, layout });
      return item;
    }

    _renderPanelRow(rowModel, overlay) {
      const first = rowModel.entries[0] && rowModel.entries[0].panel;
      if (!first) return;

      const cell = this._hoymilesCellSize(first.areaPlace || {});
      const rowSpan = Math.max(0, rowModel.maxT - rowModel.minT) * this._effectivePtdScale();
      const rowWidth = Math.max(cell.width, rowSpan + cell.width);
      const rowHeight = cell.height;
      const rowPos = this._projectPtd(rowModel.center);
      const rowStagePos = this._stagePercentFor(rowPos);
      const rowStageSize = this._stageSizeForNative(rowWidth, rowHeight);
      const rowAngle = this._panelAngleFor(first);
      const row = document.createElement("div");
      row.className = "panelRow";
      row.style.width = rowStageSize.width;
      row.style.height = rowStageSize.height;
      row.style.left = `${rowStagePos.left}%`;
      row.style.top = `${rowStagePos.top}%`;
      row.style.transform = `translate(-50%, -50%) rotate(${rowAngle}deg)`;

      for (const entry of rowModel.entries) {
        const panel = entry.panel;
        const layout = { width: cell.width, height: cell.height, angle: rowAngle };
        const item = this._createPanelItem(panel, layout);
        const localX = rowWidth / 2 + (entry.t - rowModel.centerT) * this._effectivePtdScale();
        item.style.width = `${cell.width / rowWidth * 100}%`;
        item.style.height = `${cell.height / rowHeight * 100}%`;
        item.style.left = `${localX / rowWidth * 100}%`;
        item.style.top = "50%";
        item.style.transform = "translate(-50%, -50%)";
        row.appendChild(item);
      }
      overlay.appendChild(row);
    }

    _renderFallbackPanel(panel, overlay) {
      const cell = this._hoymilesCellSize(panel.areaPlace || {});
      const rowAngle = this._panelAngleFor(panel);
      const layout = { width: cell.width, height: cell.height, angle: rowAngle };
      const snap = this._state.areaRowSnaps.get(panel.key);
      const pos = this._projectPtd({
        x: snap ? snap.x : ptdValue(panel, "x"),
        z: snap ? snap.z : ptdValue(panel, "z"),
      });
      const stagePos = this._stagePercentFor(pos);
      const stageSize = this._stageSizeForNative(cell.width, cell.height);
      const item = this._createPanelItem(panel, layout);
      item.style.width = stageSize.width;
      item.style.height = stageSize.height;
      item.style.left = `${stagePos.left}%`;
      item.style.top = `${stagePos.top}%`;
      item.style.transform = `translate(-50%, -50%) rotate(${rowAngle}deg)`;
      overlay.appendChild(item);
    }

    _signalAnchorPanels() {
      const bySerial = new Map();
      for (const panel of this._state.points) {
        const serial = normalizeSerial(panel.sn);
        if (!serial) continue;
        if (!bySerial.has(serial)) bySerial.set(serial, []);
        bySerial.get(serial).push(panel);
      }

      const anchors = [];
      const targetPort = String(this._config.signalAnchorPort || 3);
      for (const [serial, panels] of bySerial.entries()) {
        const sorted = panels.slice().sort((a, b) => Number(a.prt || 0) - Number(b.prt || 0));
        const panel = sorted.find((item) => String(item.prt) === targetPort) || sorted[0];
        if (panel) anchors.push({ serial, panel });
      }
      return anchors;
    }

    _createSignalIcon() {
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("class", "signalIcon");
      svg.setAttribute("viewBox", "0 0 24 24");
      svg.setAttribute("aria-hidden", "true");
      svg.setAttribute("focusable", "false");

      const paths = [
        "M5 12.5a10 10 0 0 1 14 0",
        "M8.5 16a5 5 0 0 1 7 0",
      ];
      for (const d of paths) {
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", d);
        path.setAttribute("fill", "none");
        path.setAttribute("stroke", "currentColor");
        path.setAttribute("stroke-width", "2.3");
        path.setAttribute("stroke-linecap", "round");
        svg.appendChild(path);
      }

      const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      dot.setAttribute("cx", "12");
      dot.setAttribute("cy", "19");
      dot.setAttribute("r", "1.7");
      dot.setAttribute("fill", "currentColor");
      svg.appendChild(dot);
      return svg;
    }

    _configureSignalMarker(marker, anchor) {
      const panel = anchor.panel;
      const metric = this._signalMetric(anchor.serial);
      const value = metric.value == null ? null : Number(metric.value);
      const isOff = this._isMissingSignalValue(value);
      const isWeak = !this._config.hasRssiThresholds && !isOff && value <= -80;
      const isOk = this._config.hasRssiThresholds && !isOff && value >= this._config.rssiOkDbm;
      const isBad = this._config.hasRssiThresholds && !isOff && value <= this._config.rssiBadDbm;
      const isWarn = this._config.hasRssiThresholds && !isOff && !isOk && !isBad;
      marker.classList.toggle("off", isOff);
      marker.classList.toggle("weak", isWeak);
      marker.classList.toggle("rssiOk", isOk);
      marker.classList.toggle("rssiWarn", isWarn);
      marker.classList.toggle("rssiBad", isBad);
      marker.title = [
        panel.area,
        `SN ${String(panel.sn || "").toUpperCase()}`,
        `Anchor port ${panel.prt}`,
        metric.entityId || "No signal entity",
        this._formatSignalMetric(metric),
      ].filter(Boolean).join("\n");

      const text = marker.querySelector(".signalValue");
      if (text) text.textContent = this._formatSignalMetric(metric);

      if (metric.entityId) {
        marker.dataset.entityId = metric.entityId;
        marker.onclick = (event) => {
          this._openMoreInfoFromClick(event, metric.entityId);
        };
      } else {
        delete marker.dataset.entityId;
        marker.onclick = null;
      }
    }

    _renderSignalMarker(anchor, overlay) {
      const panel = anchor.panel;
      const snap = this._state.areaRowSnaps.get(panel.key);
      const pos = this._projectPtd({
        x: snap ? snap.x : ptdValue(panel, "x"),
        z: snap ? snap.z : ptdValue(panel, "z"),
      });
      const stagePos = this._stagePercentFor(pos);
      const font = this._signalFontSize(panel);

      const marker = document.createElement("div");
      marker.className = "signalMarker";
      marker.style.left = `${stagePos.left}%`;
      marker.style.top = `${stagePos.top}%`;
      marker.style.setProperty("--signal-font", `${font.toFixed(2)}px`);
      marker.style.setProperty("--signal-icon", `${(font * 0.94).toFixed(2)}px`);

      marker.appendChild(this._createSignalIcon());
      const text = document.createElement("span");
      text.className = "signalValue";
      marker.appendChild(text);
      this._configureSignalMarker(marker, anchor);

      this._signalElements.set(anchor.serial, { item: marker, anchor });
      overlay.appendChild(marker);
    }

    _renderSignalMarkers(overlay) {
      for (const anchor of this._signalAnchorPanels()) {
        this._renderSignalMarker(anchor, overlay);
      }
    }

    _render() {
      if (!this._overlay || !this._state.layout) return;
      this._refreshMetricReferences();
      this._applyCameraLayerLayout();
      this._applyCamera();
      this._overlay.innerHTML = "";
      this._panelElements = new Map();
      this._signalElements = new Map();

      if (this._metricMode === "signal") {
        this._renderSignalMarkers(this._overlay);
        return;
      }

      const rendered = new Set();
      for (const row of this._state.areaRowModels) {
        this._renderPanelRow(row, this._overlay);
        for (const entry of row.entries) rendered.add(entry.panel.key);
      }
      for (const panel of this._state.points) {
        if (!rendered.has(panel.key)) this._renderFallbackPanel(panel, this._overlay);
      }
    }

    _updatePanelValues() {
      if (this._metricMode === "signal") {
        if (!this._signalElements || this._signalElements.size === 0) return false;
        for (const { item, anchor } of this._signalElements.values()) {
          this._configureSignalMarker(item, anchor);
        }
        return true;
      }

      if (!this._panelElements || this._panelElements.size === 0) return false;
      this._refreshMetricReferences();
      for (const { item, panel, layout } of this._panelElements.values()) {
        this._configurePanelItem(item, panel, layout);
      }
      return true;
    }

    _refreshMetricReferences() {
      let dailyEnergyMax = 0;
      if (this._metricMode === "daily_energy") {
        for (const panel of this._state.points) {
          const metric = this._mappedMetric(panel, "daily_energy");
          const value = this._fillValue(metric, "daily_energy");
          if (
            value != null
            && Number.isFinite(value)
            && value >= this._config.offThresholdWatts
          ) {
            dailyEnergyMax = Math.max(dailyEnergyMax, value);
          }
        }
      }
      this._metricReferences = { dailyEnergyMax };
    }

    _nativeDeltaFromCss(dx, dy) {
      const fit = this._coverFitScaleCss();
      const scale = Math.max(1, this._state.viewScale || 1);
      return {
        x: fit.x ? dx / (fit.x * scale) : dx,
        y: fit.y ? dy / (fit.y * scale) : dy,
      };
    }

    _entityTargetFromEvent(event) {
      const path = typeof event.composedPath === "function" ? event.composedPath() : [];
      for (const node of path) {
        if (node && node.dataset && node.dataset.entityId) return node;
        if (node === this._map) break;
      }
      const target = event.target && typeof event.target.closest === "function"
        ? event.target.closest("[data-entity-id]")
        : null;
      return target && this._map && this._map.contains(target) ? target : null;
    }

    _openMoreInfo(entityId) {
      if (!entityId) return;
      fireEvent(this, "hass-more-info", { entityId });
    }

    _openMoreInfoFromClick(event, entityId) {
      event.stopPropagation();
      if (this._suppressNextEntityClick) {
        event.preventDefault();
        return;
      }
      this._openMoreInfo(entityId);
    }

    _markPointerMoved(pointer) {
      if (!pointer) return false;
      const dx = pointer.x - pointer.startX;
      const dy = pointer.y - pointer.startY;
      if (Math.hypot(dx, dy) > TAP_MOVE_THRESHOLD_PX) pointer.moved = true;
      return pointer.moved;
    }

    _bindPanZoom() {
      if (!this._map || this._map.dataset.bound === "1") return;
      this._map.dataset.bound = "1";

      this._map.addEventListener("pointerdown", (event) => {
        if (event.pointerType === "mouse" && event.button !== 0) return;
        const entityTarget = this._entityTargetFromEvent(event);
        this._activePointers.set(event.pointerId, {
          x: event.clientX,
          y: event.clientY,
          startX: event.clientX,
          startY: event.clientY,
          moved: false,
          entityId: entityTarget ? entityTarget.dataset.entityId : "",
        });
        this._map.setPointerCapture(event.pointerId);
        this._dragStart = { x: event.clientX, y: event.clientY };
        this._pinchStart = this._pinchSnapshot();
      });

      this._map.addEventListener("pointermove", (event) => {
        if (!this._activePointers.has(event.pointerId)) return;
        const pointer = this._activePointers.get(event.pointerId);
        const previous = { x: pointer.x, y: pointer.y };
        pointer.x = event.clientX;
        pointer.y = event.clientY;
        this._markPointerMoved(pointer);

        if (this._activePointers.size >= 2) {
          for (const active of this._activePointers.values()) active.moved = true;
          this._map.classList.add("dragging");
          const pinch = this._pinchSnapshot();
          if (this._pinchStart && pinch && this._pinchStart.distance > 0) {
            this._state.viewScale = this._clampZoom(this._pinchStart.scale * pinch.distance / this._pinchStart.distance);
            const centerDelta = this._nativeDeltaFromCss(
              pinch.center.x - this._pinchStart.center.x,
              pinch.center.y - this._pinchStart.center.y,
            );
            this._state.offsetX = this._pinchStart.offsetX + centerDelta.x;
            this._state.offsetY = this._pinchStart.offsetY + centerDelta.y;
            this._scheduleRender();
          }
          return;
        }

        if (!pointer.moved) return;
        this._map.classList.add("dragging");
        const delta = this._nativeDeltaFromCss(event.clientX - previous.x, event.clientY - previous.y);
        this._state.offsetX += delta.x;
        this._state.offsetY += delta.y;
        this._scheduleRender();
      });

      const stopPointer = (event) => {
        const pointer = this._activePointers.get(event.pointerId);
        const isTap = pointer
          && pointer.entityId
          && !pointer.moved
          && this._activePointers.size === 1;
        this._activePointers.delete(event.pointerId);
        if (this._map.hasPointerCapture(event.pointerId)) {
          this._map.releasePointerCapture(event.pointerId);
        }
        this._pinchStart = this._pinchSnapshot();
        if (this._activePointers.size === 0) {
          this._map.classList.remove("dragging");
          this._dragStart = null;
          this._pinchStart = null;
        }
        if (pointer && pointer.entityId) {
          this._suppressNextEntityClick = true;
          window.setTimeout(() => {
            this._suppressNextEntityClick = false;
          }, 350);
        }
        if (isTap) {
          event.preventDefault();
          event.stopPropagation();
          this._openMoreInfo(pointer.entityId);
        }
      };

      this._map.addEventListener("pointerup", stopPointer);
      this._map.addEventListener("pointercancel", stopPointer);
      this._map.addEventListener("wheel", (event) => {
        event.preventDefault();
        const factor = event.deltaY < 0 ? 1.12 : 0.88;
        this._state.viewScale = this._clampZoom(this._state.viewScale * factor);
        this._scheduleRender();
      }, { passive: false });
    }

    _pinchSnapshot() {
      if (this._activePointers.size < 2) return null;
      const points = Array.from(this._activePointers.values()).slice(0, 2);
      const dx = points[0].x - points[1].x;
      const dy = points[0].y - points[1].y;
      return {
        distance: Math.hypot(dx, dy),
        center: {
          x: (points[0].x + points[1].x) / 2,
          y: (points[0].y + points[1].y) / 2,
        },
        scale: this._state.viewScale,
        offsetX: this._state.offsetX,
        offsetY: this._state.offsetY,
      };
    }

    _clampZoom(value) {
      const maxZoom = Math.max(1, this._config.maxZoom || DEFAULT_MAX_ZOOM);
      return Math.max(1, Math.min(maxZoom, value));
    }

    _showError(message) {
      this._clearError();
      const div = document.createElement("div");
      div.className = "mapError";
      div.textContent = message;
      this._map.appendChild(div);
    }

    _clearError() {
      const error = this._map && this._map.querySelector(".mapError");
      if (error) error.remove();
    }
  }

  if (!customElements.get(CARD_TYPE)) {
    customElements.define(CARD_TYPE, HoymilesLayoutCard);
  }

  window.customCards = window.customCards || [];
  window.customCards.push({
    type: `custom:${CARD_TYPE}`,
    name: "Hoymiles Layout Card",
    description: "Renders Hoymiles cloud panel layout JSON with Home Assistant port power entities.",
  });
})();
