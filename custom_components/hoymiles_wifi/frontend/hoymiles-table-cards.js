(() => {
  "use strict";

  const DOMAIN = "hoymiles_wifi";
  const UNAVAILABLE = new Set(["unknown", "unavailable", "none", ""]);
  const DEFAULT_PAGE_SIZE = 25;
  const DEFAULT_OFF_THRESHOLD_WATTS = 1;

  const CARD_TYPES = {
    inverter: "hoymiles-inverter-card",
    panels: "hoymiles-panels-card",
    dtu: "hoymiles-dtu-card",
  };

  const DEFAULT_COLUMNS = {
    inverter: [
      "inverter",
      "location",
      "phase",
      "state",
      "ac_power",
      "ac_current",
      "temperature",
      "rssi",
    ],
    panels: [
      "inverter",
      "location",
      "phase",
      "port",
      "dc_power",
      "dc_voltage",
      "dc_current",
      "dc_daily_energy",
    ],
    dtu: [
      "dtu",
      "location",
      "status",
      "ip",
      "ac_power",
      "daily_energy",
    ],
  };

  const LABELS = {
    inverter: "Inverter",
    dtu: "DTU",
    location: "Location",
    phase: "Phase",
    state: "State",
    status: "Status",
    port: "Port",
    ac_power: "AC power",
    ac_current: "AC current",
    dc_power: "DC power",
    dc_voltage: "DC voltage",
    dc_current: "DC current",
    dc_daily_energy: "Daily energy",
    dc_total_energy: "Total energy",
    daily_energy: "Daily energy",
    error_code: "Error code",
    temperature: "Temperature",
    power_factor: "Power factor",
    warning_number: "Warning number",
    rssi: "RSSI",
    ip: "IP",
    ip_address: "IP",
    signal_strength: "RSSI",
    grid_voltage: "Grid voltage",
  };

  const ENTITY_SUFFIX_ALIASES = {
    inverter: {
      ac_active_power: "ac_power",
      inverter_power_factor: "power_factor",
      inverter_temperature: "temperature",
      inverter_warning_number: "warning_number",
      rssi: "signal_strength",
    },
    panels: {
      daily_energy: "dc_daily_energy",
      port_dc_current: "dc_current",
      port_dc_daily_energy: "dc_daily_energy",
      port_dc_power: "dc_power",
      port_dc_total_energy: "dc_total_energy",
      port_dc_voltage: "dc_voltage",
      port_error_code: "error_code",
    },
    dtu: {
      ac_active_power: "ac_power",
      ac_daily_energy: "ac_daily_energy",
      daily_energy: "ac_daily_energy",
      ip: "ip_address",
      power: "ac_power",
      rssi: "signal_strength",
    },
  };

  const css = `
    :host {
      display: block;
    }

    * {
      box-sizing: border-box;
    }

    ha-card {
      overflow: hidden;
      padding: 16px;
    }

    .title {
      margin: 0 0 14px;
      font: 500 20px/1.2 var(--ha-font-family-body, system-ui, sans-serif);
      color: var(--primary-text-color);
    }

    .toolbar {
      display: grid;
      grid-template-columns: minmax(180px, 1fr) repeat(4, minmax(120px, auto));
      gap: 8px;
      align-items: center;
      margin-bottom: 10px;
    }

    input,
    select,
    button {
      min-height: 38px;
      border: 1px solid var(--divider-color);
      border-radius: 6px;
      padding: 7px 10px;
      background: var(--card-background-color);
      color: var(--primary-text-color);
      font: 400 14px/1.2 var(--ha-font-family-body, system-ui, sans-serif);
    }

    button {
      cursor: pointer;
      font-weight: 500;
    }

    .summary {
      margin: 0 0 8px;
      color: var(--secondary-text-color);
      font-size: 13px;
    }

    .tableWrap {
      overflow-x: auto;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      white-space: nowrap;
    }

    th,
    td {
      border-bottom: 1px solid var(--divider-color);
      padding: 8px 10px;
      text-align: left;
      font-size: 14px;
      vertical-align: middle;
    }

    th {
      color: var(--primary-text-color);
      font-weight: 500;
      user-select: none;
      cursor: pointer;
    }

    th.sorted {
      color: var(--primary-color);
    }

    tbody tr {
      cursor: pointer;
    }

    tbody tr:hover {
      background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.06);
    }

    .muted {
      color: var(--secondary-text-color);
    }

    .state {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }

    .dot {
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: var(--secondary-text-color);
    }

    .state.online .dot,
    .state.producing .dot {
      background: #1fa463;
    }

    .state.no_grid .dot,
    .state.zero .dot {
      background: #e09f28;
    }

    .state.unreachable .dot,
    .state.offline .dot,
    .state.off .dot {
      background: #c94848;
    }

    .pager {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 10px;
      color: var(--secondary-text-color);
      font-size: 13px;
    }

    .pager button {
      min-height: 32px;
      padding: 5px 9px;
    }

    .pager button:disabled {
      opacity: .5;
      cursor: default;
    }

    .empty {
      padding: 20px 0 6px;
      color: var(--secondary-text-color);
      text-align: center;
    }

    @media (max-width: 700px) {
      ha-card {
        padding: 12px;
      }

      .toolbar {
        grid-template-columns: 1fr 1fr;
      }

      .toolbar input {
        grid-column: 1 / -1;
      }

      .tableWrap {
        overflow: visible;
      }

      table,
      thead,
      tbody,
      tr,
      th,
      td {
        display: block;
      }

      thead {
        display: none;
      }

      tbody tr {
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        padding: 6px 0;
        margin-bottom: 8px;
      }

      td {
        display: grid;
        grid-template-columns: 42% minmax(0, 1fr);
        gap: 10px;
        border-bottom: 0;
        white-space: normal;
      }

      td::before {
        content: attr(data-label);
        color: var(--secondary-text-color);
      }
    }
  `;

  function normalizeSerial(value) {
    return String(value || "").trim().toLowerCase();
  }

  function stateObj(hass, entityId) {
    return entityId ? hass.states[entityId] : undefined;
  }

  function stateValue(hass, entityId) {
    const obj = stateObj(hass, entityId);
    return obj ? obj.state : undefined;
  }

  function isAvailable(value) {
    return !UNAVAILABLE.has(String(value ?? "").toLowerCase());
  }

  function numericState(hass, entityId) {
    const value = stateValue(hass, entityId);
    if (!isAvailable(value)) return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function displayState(hass, entityId) {
    const obj = stateObj(hass, entityId);
    if (!obj) return "";
    const unit = obj.attributes && obj.attributes.unit_of_measurement;
    return unit ? `${obj.state} ${unit}` : obj.state;
  }

  function roundDisplay(hass, entityId) {
    const value = numericState(hass, entityId);
    const obj = stateObj(hass, entityId);
    const unit = obj && obj.attributes && obj.attributes.unit_of_measurement;
    if (value == null) return displayState(hass, entityId) || "";
    return unit ? `${Math.round(value)} ${unit}` : String(Math.round(value));
  }

  function naturalCompare(left, right) {
    return String(left ?? "").localeCompare(String(right ?? ""), undefined, {
      numeric: true,
      sensitivity: "base",
    });
  }

  function slug(value) {
    return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
  }

  function labelForColumn(key) {
    if (LABELS[key]) return LABELS[key];
    return String(key || "")
      .split("_")
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
  }

  function inverterEntity(serial, suffix) {
    return `sensor.inverter_${serial}_${suffix}`;
  }

  function portEntity(serial, port, suffix) {
    return `sensor.inverter_${serial}_port_${port}_${suffix}`;
  }

  function dtuSensor(serial, suffix) {
    return `sensor.dtu_${serial}_${suffix}`;
  }

  function dtuBinary(serial) {
    return `binary_sensor.dtu_${serial}_connectivity`;
  }

  function stateBadge(value, label) {
    return `<span class="state ${value}"><span class="dot"></span>${label}</span>`;
  }

  function discoverInverterSerials(hass) {
    const serials = new Set();
    for (const entityId of Object.keys(hass.states)) {
      const match = entityId.match(/^sensor\.inverter_([a-z0-9]+)_/i);
      if (match) serials.add(normalizeSerial(match[1]));
    }
    return [...serials].sort(naturalCompare);
  }

  function discoverPanelRefs(hass) {
    const refs = [];
    for (const entityId of Object.keys(hass.states)) {
      const match = entityId.match(/^sensor\.inverter_([a-z0-9]+)_port_(\d+)_dc_power$/i);
      if (!match) continue;
      refs.push({ serial: normalizeSerial(match[1]), port: Number(match[2]) });
    }
    refs.sort((a, b) => naturalCompare(a.serial, b.serial) || a.port - b.port);
    return refs;
  }

  function discoverDtuSerials(hass) {
    const serials = new Set();
    for (const entityId of Object.keys(hass.states)) {
      let match = entityId.match(/^binary_sensor\.dtu_([a-z0-9]+)_connectivity$/i);
      if (match) {
        serials.add(normalizeSerial(match[1]));
        continue;
      }
      match = entityId.match(/^sensor\.dtu_([a-z0-9]+)_/i);
      if (match) serials.add(normalizeSerial(match[1]));
    }
    return [...serials].sort(naturalCompare);
  }

  function inverterState(hass, serial) {
    const rssi = stateValue(hass, inverterEntity(serial, "signal_strength"));
    const gridVoltage = numericState(hass, inverterEntity(serial, "grid_voltage"));
    const acPower = stateValue(hass, inverterEntity(serial, "ac_power"));

    if (!isAvailable(rssi) && gridVoltage == null && !isAvailable(acPower)) {
      return "unreachable";
    }
    if (gridVoltage != null && gridVoltage > 100) return "online";
    return "no_grid";
  }

  function panelStatus(hass, serial, port, offThresholdWatts) {
    const power = numericState(hass, portEntity(serial, port, "dc_power"));
    const voltage = numericState(hass, portEntity(serial, port, "dc_voltage"));
    const parentState = inverterState(hass, serial);

    if (parentState === "unreachable") return "off";
    if (power != null && power > offThresholdWatts) return "producing";
    if (voltage != null && voltage > 1) return "zero";
    return "off";
  }

  function dtuStatus(hass, serial) {
    const value = stateValue(hass, dtuBinary(serial));
    if (value === "on") return "online";
    if (value === "off") return "offline";
    return "unknown";
  }

  class HoymilesTableCard extends HTMLElement {
    constructor(kind) {
      super();
      this._kind = kind;
      this._config = {};
      this._hass = null;
      this._search = "";
      this._filters = {};
      this._sort = null;
      this._page = 0;
      this.attachShadow({ mode: "open" });
    }

    setConfig(config) {
      this._config = {
        title: config && config.title,
        columns: Array.isArray(config && config.columns)
          ? config.columns.map((column) => slug(column)).filter(Boolean)
          : DEFAULT_COLUMNS[this._kind],
        pageSize: Math.max(1, Number(config && (config.page_size ?? config.pageSize)) || DEFAULT_PAGE_SIZE),
        offThresholdWatts: Math.max(
          0,
          Number(config && (config.off_threshold_watts ?? config.offThresholdWatts)) || DEFAULT_OFF_THRESHOLD_WATTS,
        ),
        defaultProductionStatus: config && (config.production_status ?? config.productionStatus) || "zero",
      };
      this._filters = {};
      if (this._kind === "panels") {
        this._filters.production = this._config.defaultProductionStatus;
      }
      this._sort = { key: this._config.columns[0], dir: "asc" };
      this._page = 0;
      this._render();
    }

    set hass(hass) {
      this._hass = hass;
      this._render();
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

    _title() {
      if (this._config.title) return this._config.title;
      if (this._kind === "inverter") return "Hoymiles Inverters";
      if (this._kind === "panels") return "Hoymiles Panels";
      return "Hoymiles DTUs";
    }

    _rows() {
      if (!this._hass) return [];
      if (this._kind === "inverter") return this._inverterRows();
      if (this._kind === "panels") return this._panelRows();
      return this._dtuRows();
    }

    _inverterRows() {
      return discoverInverterSerials(this._hass).map((serial) => {
        const state = inverterState(this._hass, serial);
        const row = {
          id: serial,
          kind: "inverter",
          serial,
          entityId: inverterEntity(serial, "ac_power"),
          search: "",
          cells: {
            inverter: serial.toUpperCase(),
            location: stateValue(this._hass, inverterEntity(serial, "location")) || "",
            phase: stateValue(this._hass, inverterEntity(serial, "phase")) || "",
            state,
            ac_power: roundDisplay(this._hass, inverterEntity(serial, "ac_power")),
            ac_current: roundDisplay(this._hass, inverterEntity(serial, "ac_current")),
            temperature: roundDisplay(this._hass, inverterEntity(serial, "temperature")),
            rssi: roundDisplay(this._hass, inverterEntity(serial, "signal_strength")),
          },
          raw: {
            state,
            location: stateValue(this._hass, inverterEntity(serial, "location")) || "",
            phase: stateValue(this._hass, inverterEntity(serial, "phase")) || "",
            ac_power: numericState(this._hass, inverterEntity(serial, "ac_power")),
            ac_current: numericState(this._hass, inverterEntity(serial, "ac_current")),
            temperature: numericState(this._hass, inverterEntity(serial, "temperature")),
            rssi: numericState(this._hass, inverterEntity(serial, "signal_strength")),
          },
        };
        return this._populateConfiguredColumns(row);
      }).map((row) => ({ ...row, search: this._rowSearch(row) }));
    }

    _panelRows() {
      return discoverPanelRefs(this._hass).map(({ serial, port }) => {
        const status = panelStatus(this._hass, serial, port, this._config.offThresholdWatts);
        const row = {
          id: `${serial}-${port}`,
          kind: "panels",
          serial,
          port,
          entityId: portEntity(serial, port, "dc_power"),
          search: "",
          cells: {
            inverter: serial.toUpperCase(),
            location: stateValue(this._hass, inverterEntity(serial, "location")) || "",
            phase: stateValue(this._hass, inverterEntity(serial, "phase")) || "",
            status,
            port: port,
            dc_power: roundDisplay(this._hass, portEntity(serial, port, "dc_power")),
            dc_voltage: roundDisplay(this._hass, portEntity(serial, port, "dc_voltage")),
            dc_current: roundDisplay(this._hass, portEntity(serial, port, "dc_current")),
            dc_daily_energy: roundDisplay(this._hass, portEntity(serial, port, "dc_daily_energy")),
          },
          raw: {
            status,
            location: stateValue(this._hass, inverterEntity(serial, "location")) || "",
            phase: stateValue(this._hass, inverterEntity(serial, "phase")) || "",
            port,
            dc_power: numericState(this._hass, portEntity(serial, port, "dc_power")),
            dc_voltage: numericState(this._hass, portEntity(serial, port, "dc_voltage")),
            dc_current: numericState(this._hass, portEntity(serial, port, "dc_current")),
            dc_daily_energy: numericState(this._hass, portEntity(serial, port, "dc_daily_energy")),
          },
        };
        return this._populateConfiguredColumns(row);
      }).map((row) => ({ ...row, search: this._rowSearch(row) }));
    }

    _dtuRows() {
      return discoverDtuSerials(this._hass).map((serial) => {
        const status = dtuStatus(this._hass, serial);
        const row = {
          id: serial,
          kind: "dtu",
          serial,
          entityId: dtuBinary(serial),
          search: "",
          cells: {
            dtu: serial.toUpperCase(),
            location: stateValue(this._hass, dtuSensor(serial, "location")) || "",
            status,
            ip: displayState(this._hass, dtuSensor(serial, "ip_address")),
            ac_power: roundDisplay(this._hass, dtuSensor(serial, "ac_power")),
            daily_energy: roundDisplay(this._hass, dtuSensor(serial, "ac_daily_energy")),
          },
          raw: {
            status,
            location: stateValue(this._hass, dtuSensor(serial, "location")) || "",
            ac_power: numericState(this._hass, dtuSensor(serial, "ac_power")),
            daily_energy: numericState(this._hass, dtuSensor(serial, "ac_daily_energy")),
          },
        };
        return this._populateConfiguredColumns(row);
      }).map((row) => ({ ...row, search: this._rowSearch(row) }));
    }

    _populateConfiguredColumns(row) {
      for (const key of this._config.columns) {
        if (Object.prototype.hasOwnProperty.call(row.cells, key)) continue;
        const entityId = this._entityIdForColumn(row, key);
        if (!entityId) {
          row.cells[key] = "";
          row.raw[key] = "";
          continue;
        }
        row.cells[key] = roundDisplay(this._hass, entityId);
        const raw = numericState(this._hass, entityId);
        row.raw[key] = raw == null ? stateValue(this._hass, entityId) || "" : raw;
      }
      return row;
    }

    _entityIdForColumn(row, key) {
      const suffix = (ENTITY_SUFFIX_ALIASES[row.kind] && ENTITY_SUFFIX_ALIASES[row.kind][key]) || key;
      if (row.kind === "inverter") return inverterEntity(row.serial, suffix);
      if (row.kind === "panels") return portEntity(row.serial, row.port, suffix);
      if (row.kind === "dtu") return dtuSensor(row.serial, suffix);
      return "";
    }

    _rowSearch(row) {
      return Object.values(row.cells).join(" ").toLowerCase();
    }

    _filterOptions(rows, key) {
      return [...new Set(rows.map((row) => row.raw[key]).filter((value) => value != null && value !== ""))]
        .sort(naturalCompare);
    }

    _filteredRows(rows) {
      const search = this._search.trim().toLowerCase();
      return rows.filter((row) => {
        if (search && !row.search.includes(search)) return false;
        if (this._filters.location && row.raw.location !== this._filters.location) return false;
        if (this._filters.phase && row.raw.phase !== this._filters.phase) return false;
        if (this._filters.state && row.raw.state !== this._filters.state) return false;
        if (this._filters.status && row.raw.status !== this._filters.status) return false;
        if (
          this._filters.production
          && this._filters.production !== "all"
          && row.raw.status !== this._filters.production
        ) return false;
        return true;
      });
    }

    _sortedRows(rows) {
      if (!this._sort || !this._sort.key) return rows;
      const dir = this._sort.dir === "desc" ? -1 : 1;
      return [...rows].sort((left, right) => {
        const leftValue = left.raw[this._sort.key] ?? left.cells[this._sort.key];
        const rightValue = right.raw[this._sort.key] ?? right.cells[this._sort.key];
        if (typeof leftValue === "number" && typeof rightValue === "number") {
          return (leftValue - rightValue) * dir;
        }
        return naturalCompare(leftValue, rightValue) * dir;
      });
    }

    _visibleRows(rows) {
      const start = this._page * this._config.pageSize;
      return rows.slice(start, start + this._config.pageSize);
    }

    _render() {
      if (!this.shadowRoot) return;
      const rows = this._rows();
      const filtered = this._sortedRows(this._filteredRows(rows));
      const pageCount = Math.max(1, Math.ceil(filtered.length / this._config.pageSize));
      if (this._page >= pageCount) this._page = pageCount - 1;
      const visible = this._visibleRows(filtered);

      this.shadowRoot.innerHTML = `
        <style>${css}</style>
        <ha-card>
          <h2 class="title">${this._escape(this._title())}</h2>
          ${this._toolbar(rows)}
          <p class="summary">${filtered.length} matched of ${rows.length}</p>
          <div class="tableWrap">
            ${visible.length ? this._table(visible) : '<div class="empty">No matching Hoymiles entities</div>'}
          </div>
          ${this._pager(filtered.length, pageCount)}
        </ha-card>
      `;
      this._bindEvents();
    }

    _toolbar(rows) {
      const locationOptions = this._filterOptions(rows, "location");
      const phaseOptions = this._filterOptions(rows, "phase");
      const stateFilter = this._kind === "inverter"
        ? this._select("state", "State", ["online", "no_grid", "unreachable"])
        : "";
      const statusFilter = this._kind === "dtu"
        ? this._select("status", "Status", ["online", "offline", "unknown"])
        : "";
      const productionFilter = this._kind === "panels"
        ? this._select("production", "Production", ["all", "producing", "zero", "off"])
        : "";

      return `
        <div class="toolbar">
          <input class="search" type="search" placeholder="Search" value="${this._escapeAttr(this._search)}">
          ${this._select("location", "Location", locationOptions)}
          ${this._kind !== "dtu" ? this._select("phase", "Phase", phaseOptions) : ""}
          ${stateFilter}${statusFilter}${productionFilter}
          <select class="pageSize" aria-label="Rows per page">
            ${this._pageSizeOptions().map((size) => `
              <option value="${size}" ${size === this._config.pageSize ? "selected" : ""}>${size} rows</option>
            `).join("")}
          </select>
        </div>
      `;
    }

    _pageSizeOptions() {
      return [...new Set([10, 25, 50, 100, this._config.pageSize])]
        .filter((size) => Number.isFinite(size) && size > 0)
        .sort((left, right) => left - right);
    }

    _select(key, label, options) {
      const value = this._filters[key] || "";
      return `
        <select data-filter="${key}" aria-label="${this._escapeAttr(label)}">
          <option value="">${this._escape(label)}</option>
          ${options.map((option) => `
            <option value="${this._escapeAttr(option)}" ${String(option) === String(value) ? "selected" : ""}>
              ${this._escape(this._optionLabel(option))}
            </option>
          `).join("")}
        </select>
      `;
    }

    _optionLabel(value) {
      const labels = {
        no_grid: "No grid",
        online: "Online",
        unreachable: "Unreachable",
        offline: "Offline",
        unknown: "Unknown",
        producing: "Producing",
        zero: "Zero production",
        off: "Off",
        all: "All",
      };
      return labels[value] || value;
    }

    _table(rows) {
      return `
        <table>
          <thead>
            <tr>
              ${this._config.columns.map((key) => `
                <th data-sort="${this._escapeAttr(key)}" class="${this._sort && this._sort.key === key ? "sorted" : ""}">
                  ${this._escape(labelForColumn(key))}
                  ${this._sort && this._sort.key === key ? (this._sort.dir === "asc" ? " ^" : " v") : ""}
                </th>
              `).join("")}
            </tr>
          </thead>
          <tbody>
            ${rows.map((row) => `
              <tr data-entity-id="${this._escapeAttr(row.entityId)}">
                ${this._config.columns.map((key) => `
                  <td data-label="${this._escapeAttr(labelForColumn(key))}">
                    ${this._cell(row, key)}
                  </td>
                `).join("")}
              </tr>
            `).join("")}
          </tbody>
        </table>
      `;
    }

    _cell(row, key) {
      const value = row.cells[key] ?? "";
      if (key === "state" || key === "status") {
        return stateBadge(row.raw[key], this._optionLabel(row.raw[key]));
      }
      return value === "" ? '<span class="muted">-</span>' : this._escape(value);
    }

    _pager(total, pageCount) {
      const start = total === 0 ? 0 : this._page * this._config.pageSize + 1;
      const end = Math.min(total, (this._page + 1) * this._config.pageSize);
      return `
        <div class="pager">
          <button class="prev" ${this._page <= 0 ? "disabled" : ""}>Prev</button>
          <span>${start}-${end} of ${total}</span>
          <button class="next" ${this._page >= pageCount - 1 ? "disabled" : ""}>Next</button>
        </div>
      `;
    }

    _bindEvents() {
      const root = this.shadowRoot;
      const search = root.querySelector(".search");
      if (search) {
        search.addEventListener("input", (event) => {
          this._search = event.target.value;
          this._page = 0;
          this._render();
        });
      }

      for (const select of root.querySelectorAll("select[data-filter]")) {
        select.addEventListener("change", (event) => {
          const key = event.target.dataset.filter;
          this._filters[key] = event.target.value;
          this._page = 0;
          this._render();
        });
      }

      const pageSize = root.querySelector(".pageSize");
      if (pageSize) {
        pageSize.addEventListener("change", (event) => {
          this._config.pageSize = Number(event.target.value) || DEFAULT_PAGE_SIZE;
          this._page = 0;
          this._render();
        });
      }

      for (const header of root.querySelectorAll("th[data-sort]")) {
        header.addEventListener("click", (event) => {
          const key = event.currentTarget.dataset.sort;
          if (this._sort && this._sort.key === key) {
            this._sort.dir = this._sort.dir === "asc" ? "desc" : "asc";
          } else {
            this._sort = { key, dir: "asc" };
          }
          this._render();
        });
      }

      const prev = root.querySelector(".prev");
      if (prev) {
        prev.addEventListener("click", () => {
          this._page = Math.max(0, this._page - 1);
          this._render();
        });
      }

      const next = root.querySelector(".next");
      if (next) {
        next.addEventListener("click", () => {
          this._page += 1;
          this._render();
        });
      }

      for (const row of root.querySelectorAll("tbody tr[data-entity-id]")) {
        row.addEventListener("click", (event) => {
          const entityId = event.currentTarget.dataset.entityId;
          if (!entityId || !this._hass.states[entityId]) return;
          this.dispatchEvent(new CustomEvent("hass-more-info", {
            bubbles: true,
            composed: true,
            detail: { entityId },
          }));
        });
      }
    }

    _escape(value) {
      return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    }

    _escapeAttr(value) {
      return this._escape(value).replace(/"/g, "&quot;");
    }
  }

  class HoymilesInverterCard extends HoymilesTableCard {
    constructor() {
      super("inverter");
    }
  }

  class HoymilesPanelsCard extends HoymilesTableCard {
    constructor() {
      super("panels");
    }
  }

  class HoymilesDtuCard extends HoymilesTableCard {
    constructor() {
      super("dtu");
    }
  }

  if (!customElements.get(CARD_TYPES.inverter)) {
    customElements.define(CARD_TYPES.inverter, HoymilesInverterCard);
  }
  if (!customElements.get(CARD_TYPES.panels)) {
    customElements.define(CARD_TYPES.panels, HoymilesPanelsCard);
  }
  if (!customElements.get(CARD_TYPES.dtu)) {
    customElements.define(CARD_TYPES.dtu, HoymilesDtuCard);
  }

  window.customCards = window.customCards || [];
  window.customCards.push(
    {
      type: CARD_TYPES.inverter,
      name: "Hoymiles inverter table",
      description: "Lists Hoymiles inverters with search, filters, sorting, and pagination.",
    },
    {
      type: CARD_TYPES.panels,
      name: "Hoymiles panel table",
      description: "Lists Hoymiles panel ports with search, filters, sorting, and pagination.",
    },
    {
      type: CARD_TYPES.dtu,
      name: "Hoymiles DTU table",
      description: "Lists Hoymiles DTUs with search, filters, sorting, and pagination.",
    },
  );
})();
