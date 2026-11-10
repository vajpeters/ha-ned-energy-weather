/* Bundled Lovelace card. All data comes through the authenticated HA connection. */
const command = "ned_energy_weather/";
const day = 86400000;
const colors = ["#008db1", "#e07b26", "#9767d3", "#298d62"];
const units = {capacity: "kW", volume: "kWh", percentage: "%", emission: "kg", emission_factor: "kg/kWh"};
const key = (dataset) => dataset.type_id + ":" + dataset.activity;

class NedEnergyWeatherCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this.generation = 0;
  }

  setConfig(config) {
    this.config = config;
    this.catalog = null;
    this.generation++;
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; color: var(--primary-text-color); }
        .body { padding: 16px; }
        .controls { display: flex; flex-wrap: wrap; align-items: end; gap: 10px; }
        label { display: grid; gap: 4px; font-size: .85rem; min-width: 0; }
        select, button {
          color: var(--primary-text-color); background: var(--card-background-color);
          border: 1px solid var(--divider-color); border-radius: 5px;
          padding: 6px; font: inherit; max-width: 100%; min-height: 34px;
        }
        .datasets { flex: 1 1 180px; }
        .datasets select { width: 100%; }
        button { cursor: pointer; color: var(--primary-color); }
        svg { display: block; width: 100%; height: 235px; touch-action: pan-y; }
        .axis { stroke: var(--divider-color, #999); }
        text { fill: var(--secondary-text-color); font: 10px sans-serif; }
        .legend { display: flex; flex-wrap: wrap; gap: 5px 14px; font-size: .8rem; }
        .swatch { display: inline-block; width: 16px; margin-right: 4px; vertical-align: middle; }
        .detail { min-height: 2em; font-size: .85rem; }
        [role=status] { color: var(--secondary-text-color); }
      </style>
      <ha-card>
        <section class="body">
          <h2></h2>
          <div class="controls">
            <label>Gebied<select id="area"><option value="0">Nederland</option></select></label>
            <label class="datasets">Reeksen (max. 4)<select id="datasets" multiple size="4"></select></label>
            <label>Resolutie<select id="granularity">
              <option value="15min">Kwartier</option><option value="hour">Uur</option><option value="day">Dag</option>
            </select></label>
            <label>Historie<select id="past"><option>1</option><option>3</option><option>7</option><option>14</option><option>30</option></select></label>
            <label>Vooruit<select id="future"><option>0</option><option>1</option><option>3</option><option>7</option></select></label>
            <label>Meetveld<select id="field"></select></label>
            <button id="load">Ophalen</button>
          </div>
          <p id="status" role="status"></p>
          <svg id="chart" role="img" aria-label="NED-tijdreeks"></svg>
          <div id="detail" class="detail"></div>
          <div id="legend" class="legend"></div>
        </section>
      </ha-card>`;
    this.$("h2").textContent = config.title || "NED Energieweerbericht";
    for (const [field, unit] of Object.entries(units)) {
      this.$("#field").add(new Option(field.replace("_", " ") + " (" + unit + ")", field));
    }
    this.$("#granularity").value = ["15min", "hour", "day"].includes(config.granularity)
      ? config.granularity : "hour";
    this.$("#past").value = "3";
    this.$("#future").value = "1";
    this.$("#area").onchange = () => this.populate();
    this.$("#load").onclick = () => this.catalog ? this.load() : this.initialize();
    if (this._hass) this.initialize();
  }

  $(selector) {
    return this.shadowRoot.querySelector(selector);
  }

  set hass(hass) {
    this._hass = hass;
    if (this.config && !this.catalog && !this.initializing) this.initialize();
  }

  getCardSize() { return 6; }

  async initialize() {
    const version = this.generation;
    this.initializing = true;
    this.$("#status").textContent = "Catalogus laden…";
    try {
      const catalog = await this._hass.callWS({type: command + "catalog"});
      if (version !== this.generation) return;
      this.catalog = catalog;
      this.$("#area").add(new Option(catalog.province.name, catalog.province.point_id));
      if (this.config.area === "province") this.$("#area").value = catalog.province.point_id;
      this.populate();
      await this.load();
    } catch (error) {
      if (version === this.generation) this.$("#status").textContent = error.message || "Catalogus niet beschikbaar.";
    } finally {
      this.initializing = false;
    }
  }

  populate() {
    const point = Number(this.$("#area").value);
    const select = this.$("#datasets");
    const selected = [...select.selectedOptions].map((option) => option.value);
    const wanted = selected.length ? selected : (this.config.datasets || ["2:1", "1:1"]);
    select.replaceChildren();
    const groups = new Map();
    for (const dataset of this.catalog.datasets.filter((item) => item.point_id === point)) {
      if (!groups.has(dataset.category)) {
        const group = document.createElement("optgroup");
        group.label = dataset.category.replaceAll("_", " ");
        groups.set(dataset.category, group);
        select.append(group);
      }
      const option = new Option(dataset.name, key(dataset));
      option.selected = wanted.slice(0, 4).includes(option.value);
      groups.get(dataset.category).append(option);
    }
    if (!select.selectedOptions.length && select.options.length) select.options[0].selected = true;
  }

  async load() {
    const version = ++this.generation;
    const status = this.$("#status");
    const selected = [...this.$("#datasets").selectedOptions].map((option) => option.value);
    if (!selected.length || selected.length > 4) {
      status.textContent = "Kies één tot vier reeksen.";
      return;
    }
    status.textContent = "Tijdreeksen laden…";
    const area = Number(this.$("#area").value);
    const granularity = this.$("#granularity").value;
    const field = this.$("#field").value;
    const now = Date.now();
    const start = now - day * Number(this.$("#past").value);
    const future = Number(this.$("#future").value);
    const end = now + day * future;
    const jobs = [];
    for (const [index, datasetKey] of selected.entries()) {
      const dataset = this.catalog.datasets.find((item) => item.point_id === area && key(item) === datasetKey);
      if (!dataset.fields.includes(field)) continue;
      const query = {type: command + "get_series", area, granularity,
        type_id: dataset.type_id, activity: dataset.activity};
      const add = (classification, label, from, to, dash) => {
        jobs.push(this._hass.callWS({...query, classification,
          start: new Date(from).toISOString(), end: new Date(to).toISOString()
        }).then((response) => ({
          label: dataset.name + " · " + label, color: colors[index], dash,
          stale: response.availability === "stale",
          points: response.records
            .filter((row) => Number.isFinite(row[field]))
            .map((row) => ({time: Date.parse(row.valid_from), value: row[field]})),
        })));
      };
      add("actual", "Actueel", start, now, "");
      if (dataset.forecast_days) {
        if (future) add("forecast", "Voorspeld", now, end, "7 4");
        if (granularity === "hour") add("historical_forecast", "Eerdere voorspelling", start, now, "2 4");
      }
    }
    const results = await Promise.allSettled(jobs);
    if (version !== this.generation) return;
    const traces = results.filter((result) => result.status === "fulfilled").map((result) => result.value);
    const errors = results.filter((result) => result.status === "rejected");
    const visible = traces.filter((trace) => trace.points.length);
    const notices = [];
    if (!visible.length) notices.push("Geen meetwaarden voor deze selectie.");
    if (traces.some((trace) => trace.stale)) notices.push("Een deel van de waarden komt uit een verlopen cache.");
    if (errors.length) notices.push("Ophalen mislukt voor " + errors.length + " reeks(en): " + (errors[0].reason?.message || "NED-fout"));
    status.textContent = notices.join(" ");
    this.draw(visible, start, end, units[field], granularity);
  }

  draw(traces, start, end, unit, granularity) {
    const chart = this.$("#chart"), legend = this.$("#legend"), detail = this.$("#detail");
    chart.onpointermove = null;
    chart.onpointerleave = null;
    chart.replaceChildren();
    legend.replaceChildren();
    detail.textContent = "";
    if (!traces.length) return;
    const width = Math.max(280, chart.clientWidth || 420);
    chart.setAttribute("viewBox", "0 0 " + width + " 235");
    const left = 59, right = width - 14, top = 15, bottom = 197;
    const values = traces.flatMap((trace) => trace.points.map((point) => point.value));
    const low = Math.min(...values), high = Math.max(...values);
    const pad = (high - low || Math.abs(high) || 1) * .05;
    const min = low - pad, max = high + pad;
    const x = (time) => left + (time - start) / (end - start) * (right - left);
    const y = (value) => bottom - (value - min) / (max - min) * (bottom - top);
    const language = this._hass.language || "nl";
    const timezone = this._hass.config?.time_zone;
    const fmt = new Intl.DateTimeFormat(language, {timeZone: timezone, dateStyle: "short", timeStyle: "short"});
    const short = new Intl.DateTimeFormat(language, {
      timeZone: timezone, month: "short", day: "numeric",
      ...(end - start <= day * 2 ? {hour: "2-digit", minute: "2-digit"} : {}),
    });
    const number = new Intl.NumberFormat(language, {notation: "compact", maximumFractionDigits: 2});
    const add = (tag, attrs, label) => {
      const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
      for (const [name, value] of Object.entries(attrs)) element.setAttribute(name, value);
      if (label !== undefined) element.textContent = label;
      chart.append(element);
      return element;
    };
    add("text", {x: 4, y: 12}, unit);
    for (let i = 0; i <= 4; i++) {
      const value = min + (max - min) * i / 4;
      add("line", {x1: left, x2: right, y1: y(value), y2: y(value), class: "axis"});
      add("text", {x: left - 6, y: y(value) + 3, "text-anchor": "end"}, number.format(value));
    }
    for (let i = 0; i <= 3; i++) {
      const time = start + (end - start) * i / 3;
      add("text", {x: x(time), y: 216, "text-anchor": i === 3 ? "end" : i === 0 ? "start" : "middle"}, short.format(time));
    }
    const gap = {"15min": 900000, hour: 3600000, day}[granularity] * 1.6;
    for (const trace of traces) {
      let previous;
      let path = "";
      for (const point of trace.points) {
        const connects = previous && point.time - previous.time <= gap;
        path += (connects ? "L" : "M") + x(point.time) + " " + y(point.value);
        if (!connects) add("circle", {cx: x(point.time), cy: y(point.value), r: 2, fill: trace.color});
        previous = point;
      }
      add("path", {d: path, fill: "none", stroke: trace.color, "stroke-width": 2, "stroke-dasharray": trace.dash});
      const entry = document.createElement("span");
      const swatch = document.createElement("span");
      swatch.className = "swatch";
      swatch.style.borderTop = "2px " + (trace.dash ? "dashed " : "solid ") + trace.color;
      entry.append(swatch, trace.label);
      legend.append(entry);
    }
    const cursor = add("line", {y1: top, y2: bottom, stroke: "currentColor", visibility: "hidden"});
    chart.onpointermove = (event) => {
      const rect = chart.getBoundingClientRect();
      const position = (event.clientX - rect.left) / rect.width * width;
      const time = start + (position - left) / (right - left) * (end - start);
      let closest;
      for (const trace of traces) {
        for (const point of trace.points) {
          const distance = Math.abs(point.time - time);
          if (!closest || distance < closest.distance) closest = {point, distance, label: trace.label};
        }
      }
      const {point, label} = closest;
      cursor.setAttribute("visibility", "visible");
      cursor.setAttribute("x1", x(point.time));
      cursor.setAttribute("x2", x(point.time));
      detail.textContent = fmt.format(point.time) + " · " + label + " · " + point.value.toLocaleString(language) + " " + unit;
    };
    chart.onpointerleave = () => cursor.setAttribute("visibility", "hidden");
  }
}

if (!customElements.get("ned-energy-weather-card")) {
  customElements.define("ned-energy-weather-card", NedEnergyWeatherCard);
  window.customCards = window.customCards || [];
  window.customCards.push({type: "ned-energy-weather-card", name: "NED Energieweerbericht"});
}
