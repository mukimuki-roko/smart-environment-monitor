let tableRows = window.sensorRows || [];
let fieldnames = window.sensorFieldnames || [];
let fieldLabels = window.sensorFieldLabels || {};
let filteredRows = [];
let sortedRows = [];
let pagedRows = [];
let chartRows = [];
let healthClients = [];
let activeView = "table";
let healthStream;
let sortState = { field: "datetime", direction: "desc" };
let paginationState = { page: 1, pageSize: 25 };
let chartLimit = 50;
let modalFilterState = {};

const textFields = ["client_id", "region"];
const numericFields = ["temperature", "humidity", "pressure", "co2"];
const detailOnlyFields = new Set(["session_id", "sequence"]);

const chartPanel = document.querySelector('[data-view-panel="graph"]');
const healthPanel = document.querySelector('[data-view-panel="health"]');
const healthList = document.querySelector("[data-health-list]");
const healthEmpty = document.querySelector("[data-health-empty]");
const healthEmptyTitle = document.querySelector("[data-health-empty-title]");
const healthEmptyMessage = document.querySelector("[data-health-empty-message]");
const chartCanvases = document.querySelectorAll("[data-chart-metric]");
const chartPanes = document.querySelectorAll("[data-graph-pane]");
const chartDownloadButtons = document.querySelectorAll("[data-graph-download]");
const chartModal = document.querySelector("[data-chart-modal]");
const chartModalTitle = document.querySelector("[data-chart-modal-title]");
const chartModalCanvas = document.querySelector("[data-chart-modal-canvas]");
const chartModalCloseButtons = document.querySelectorAll("[data-chart-modal-close]");
const chartModalDownloadButton = document.querySelector("[data-chart-modal-download]");
const chartLimitSelect = document.querySelector("[data-chart-limit]");
const clientIdSuggestions = document.querySelector("#client-id-suggestions");
const regionSuggestions = document.querySelector("#region-suggestions");
const healthClientIdSuggestions = document.querySelector("#health-client-id-suggestions");
const healthRegionSuggestions = document.querySelector("#health-region-suggestions");
const modalFilterControls = document.querySelectorAll("[data-modal-filter-min], [data-modal-filter-max], [data-modal-filter-value], [data-modal-filter-op], [data-modal-text-op], [data-modal-text-value]");
const modalFilterOp = document.querySelector("[data-modal-filter-op]");
const modalChartLimitSelect = document.querySelector("[data-modal-chart-limit]");
const modalMetricLabel = document.querySelector("[data-modal-metric-label]");
const modalMetricMin = document.querySelector("[data-modal-filter-min='value']");
const modalMetricMax = document.querySelector("[data-modal-filter-max='value']");
const modalMetricValue = document.querySelector("[data-modal-filter-value]");
const modalDatetimeMin = document.querySelector("[data-modal-filter-min='datetime']");
const modalDatetimeMax = document.querySelector("[data-modal-filter-max='datetime']");
const modalFilterClearButton = document.querySelector("[data-modal-filter-clear]");
const tablePanel = document.querySelector(".table-wrap");
const table = document.querySelector("table");
const tableHeadRow = document.querySelector("thead tr");
const tableBody = document.querySelector("tbody");
const toolbar = document.querySelector(".toolbar");
const filterPanel = document.querySelector(".filter-panel");
const paginationBars = document.querySelectorAll(".pagination-bar");
const emptyState = document.querySelector(".empty-state");
const refreshButton = document.querySelector("[data-refresh-button]");
const clearFiltersButton = document.querySelector("[data-clear-filters]");
const sensorSummary = document.querySelector("[data-sensor-summary]");
const pageSummaries = document.querySelectorAll("[data-page-summary]");
const pageCurrentLabels = document.querySelectorAll("[data-page-current]");
const pageSizeSelects = document.querySelectorAll("[data-page-size]");
const pageSizeCustomInputs = document.querySelectorAll("[data-page-size-custom]");
const prevPageButtons = document.querySelectorAll("[data-page-prev]");
const nextPageButtons = document.querySelectorAll("[data-page-next]");
const viewButtons = document.querySelectorAll("[data-view-button]");
const filterControls = document.querySelectorAll("[data-filter-op], [data-filter-value], [data-filter-min], [data-filter-max]");
const numericFilterOps = document.querySelectorAll("[data-filter-op='temperature'], [data-filter-op='humidity'], [data-filter-op='pressure'], [data-filter-op='co2']");
const healthFilterControls = document.querySelectorAll("[data-health-filter]");
const clearHealthFiltersButton = document.querySelector("[data-clear-health-filters]");

const fallbackFieldLabels = {
    client_id: "端末ID",
    region: "地域",
    datetime: "日時",
    session_id: "セッションID",
    sequence: "送信番号",
    temperature: "温度",
    humidity: "湿度",
    pressure: "気圧",
    co2: "CO2",
};

const metricLabels = {
    temperature: "温度",
    humidity: "湿度",
    pressure: "気圧",
    co2: "CO2",
};

const metricColors = {
    temperature: "#d14343",
    humidity: "#2563eb",
    pressure: "#7c3aed",
    co2: "#0f766e",
};

const metricFileNames = {
    temperature: "temperature",
    humidity: "humidity",
    pressure: "pressure",
    co2: "co2",
};

function currentView() {
    return activeView;
}

function setView(view) {
    activeView = view;
    const showGraph = view === "graph";
    const showHealth = view === "health";
    const showSearch = view === "table" || showGraph;
    const hasRows = tableRows.length > 0;

    if (showGraph) {
        chartPanel.before(filterPanel);
    }

    chartPanel.hidden = !showGraph || !hasRows;
    healthPanel.hidden = !showHealth;
    tablePanel.hidden = view !== "table" || !hasRows;
    filterPanel.hidden = !showSearch || !hasRows;
    paginationBars.forEach((paginationBar) => {
        paginationBar.hidden = view !== "table" || !hasRows;
    });
    emptyState.hidden = view !== "table" || hasRows;

    viewButtons.forEach((button) => {
        button.classList.toggle("is-active", button.dataset.viewButton === view);
    });

    if (showGraph && hasRows) {
        drawAllCharts();
    }
}

async function refreshDashboardData() {
    const view = currentView();

    refreshButton.disabled = true;

    try {
        const [sensorResponse, healthResponse] = await Promise.all([
            fetch("/api/sensor-data", { cache: "no-store" }),
            fetch("/api/health", { cache: "no-store" }),
        ]);

        if (!sensorResponse.ok || !healthResponse.ok) {
            throw new Error("更新に失敗しました");
        }

        updateSensorData(await sensorResponse.json(), { preservePage: true });
        updateHealthData(await healthResponse.json());
        setView(view);
    } catch (error) {
        console.error(error);
    } finally {
        refreshButton.disabled = false;
    }
}

async function refreshHealthData() {
    try {
        const response = await fetch("/api/health", { cache: "no-store" });
        if (!response.ok) {
            throw new Error(`ヘルス更新に失敗しました: ${response.status}`);
        }
        updateHealthData(await response.json());
    } catch (error) {
        console.error(error);
    }
}

function connectHealthStream() {
    if (!window.EventSource || healthStream) {
        return;
    }

    healthStream = new EventSource("/api/health/stream");
    healthStream.addEventListener("health", () => {
        refreshHealthData();
    });
    healthStream.addEventListener("error", () => {
        // EventSource reconnects automatically using the retry interval sent by the server.
    });
}

function updateSensorData(payload, options = {}) {
    tableRows = payload.rows || [];
    fieldnames = payload.fieldnames || [];
    fieldLabels = payload.field_labels || fieldLabels;

    renderTextSuggestions();
    renderSummary(payload);
    updateDataViews({ preservePage: options.preservePage });
    renderEmptyState();
}

function renderTextSuggestions() {
    renderSuggestions(clientIdSuggestions, "client_id");
    renderSuggestions(regionSuggestions, "region");
}

function renderSuggestions(datalist, field) {
    if (!datalist) {
        return;
    }

    const values = [...new Set(
        tableRows
            .map((row) => String(row[field] || "").trim())
            .filter(Boolean),
    )].sort((a, b) => a.localeCompare(b, "ja", { numeric: true, sensitivity: "base" }));

    datalist.replaceChildren(...values.map((value) => {
        const option = document.createElement("option");
        option.value = value;
        return option;
    }));
}

function updateHealthData(payload) {
    healthClients = payload.clients || [];
    renderHealthSuggestions();
    renderHealth();
}

function renderHealthSuggestions() {
    renderHealthSuggestionValues(healthClientIdSuggestions, "client_id");
    renderHealthSuggestionValues(healthRegionSuggestions, "region");
}

function renderHealthSuggestionValues(datalist, field) {
    if (!datalist) {
        return;
    }
    const values = [...new Set(
        healthClients
            .map((client) => String(client.client?.[field] || "").trim())
            .filter(Boolean),
    )].sort((a, b) => a.localeCompare(b, "ja", { numeric: true, sensitivity: "base" }));
    datalist.replaceChildren(...values.map((value) => {
        const option = document.createElement("option");
        option.value = value;
        return option;
    }));
}

function healthFilterValue(field) {
    return document.querySelector(`[data-health-filter="${field}"]`)?.value.trim().toLowerCase() || "";
}

function filteredHealthClients() {
    return healthClients.filter((client) => textFields.every((field) => {
        const query = healthFilterValue(field);
        return !query || String(client.client?.[field] || "").toLowerCase().includes(query);
    }));
}

function clearHealthFilters() {
    healthFilterControls.forEach((control) => {
        control.value = "";
    });
    renderHealth();
}

function renderHealth() {
    if (!healthList || !healthEmpty) {
        return;
    }

    const expandedClientIds = new Set(
        [...healthList.querySelectorAll(".health-card[data-client-id] details[open]")]
            .map((details) => details.closest(".health-card")?.dataset.clientId)
            .filter(Boolean),
    );
    const clients = filteredHealthClients();
    healthList.replaceChildren(...clients.map((client) => createHealthCard(
        client,
        expandedClientIds.has(client.client?.client_id),
    )));
    healthEmpty.hidden = clients.length > 0;
    if (healthClients.length === 0) {
        healthEmptyTitle.textContent = "ヘルスデータがありません";
        healthEmptyMessage.textContent = "クライアントからヘルスデータが届くと、ここに表示されます。";
    } else if (clients.length === 0) {
        healthEmptyTitle.textContent = "条件に一致するヘルスデータがありません";
        healthEmptyMessage.textContent = "端末IDまたは地域の検索条件を変更してください。";
    }
}

function createHealthCard(client, detailsOpen = false) {
    const card = document.createElement("article");
    card.className = "health-card";
    card.dataset.clientId = client.client?.client_id || "";
    const header = document.createElement("header");
    header.className = "health-card-header";
    const title = document.createElement("div");
    const heading = document.createElement("h3");
    heading.textContent = client.client?.client_id || "不明な端末";
    const region = document.createElement("p");
    region.textContent = `${client.client?.region || "地域未設定"} / 最終受信 ${client.received_at || "-"}`;
    title.append(heading, region);
    const badge = document.createElement("span");
    badge.className = `health-status health-status-${client.status === "online" ? "online" : "offline"}`;
    badge.textContent = client.status === "online" ? "オンライン" : "オフライン";
    const actions = document.createElement("div");
    actions.className = "health-card-actions";
    const download = document.createElement("a");
    download.className = "secondary-button";
    download.href = `/api/health/${encodeURIComponent(client.client?.client_id || "")}/download`;
    download.textContent = "CSV保存";
    download.setAttribute("aria-label", `${client.client?.client_id || "端末"} のヘルス履歴CSVを保存`);
    actions.append(badge, download);
    header.append(title, actions);

    const summary = document.createElement("p");
    summary.className = "health-summary";
    const errors = healthErrors(client);
    summary.textContent = errors.length ? errors.join(" / ") : "異常は報告されていません";

    const details = document.createElement("details");
    details.open = detailsOpen;
    const detailsSummary = document.createElement("summary");
    detailsSummary.textContent = "詳細を表示";
    details.appendChild(detailsSummary);
    const groups = document.createElement("div");
    groups.className = "health-detail-groups";
    SENSOR_NAMES.forEach((sensorName) => {
        groups.appendChild(createHealthGroup(sensorName.toUpperCase(), client.sensor?.[sensorName], [
            ["接続", "connect"], ["読み取り", "read"], ["読取成功数", "read_count"],
            ["失敗数", "fail_count"], ["連続失敗数", "consecutive_fail_count"],
            ["最終成功", "last_success_at"], ["最終失敗", "last_failed_at"], ["エラー", "error"],
        ]));
    });
    groups.appendChild(createHealthGroup("サーバー送信", client.server_send, [
        ["成功", "success"], ["送信成功数", "success_count"], ["server受信数", "received_count"], ["最終ACK連番", "last_ack_sequence"], ["失敗数", "fail_count"], ["連続失敗数", "consecutive_fail_count"],
        ["最終成功", "last_success_at"], ["最終失敗", "last_failed_at"], ["HTTPステータス", "last_status_code"], ["エラー", "error"],
    ]));
    groups.appendChild(createHealthGroup("ヘルスレポート", client.health_report, [
        ["成功", "success"], ["成功数", "success_count"], ["失敗数", "fail_count"], ["連続失敗数", "consecutive_fail_count"],
        ["最終成功", "last_success_at"], ["最終失敗", "last_failed_at"], ["HTTPステータス", "last_status_code"], ["エラー", "error"],
    ]));
    groups.appendChild(createHealthGroup("ランタイム", client.runtime, [
        ["起動時刻", "started_at"], ["最終ループ", "last_loop_at"], ["ループ回数", "loop_count"], ["稼働秒数", "uptime_seconds"],
    ]));
    details.appendChild(groups);
    card.append(header, summary, details);
    return card;
}

const SENSOR_NAMES = ["bme280", "dht22", "mhz19c"];

function healthErrors(client) {
    const errors = [];
    SENSOR_NAMES.forEach((name) => {
        const sensor = client.sensor?.[name];
        if (sensor && (!sensor.connect || !sensor.read || sensor.error)) {
            errors.push(`${sensor.name || name}: ${sensor.error || "読み取り異常"}`);
        }
    });
    if (client.server_send && (!client.server_send.success || client.server_send.error)) {
        errors.push(`サーバー送信: ${client.server_send.error || "失敗"}`);
    }
    return errors;
}

function createHealthGroup(title, values, fields) {
    const group = document.createElement("section");
    group.className = "health-detail-group";
    const heading = document.createElement("h4");
    heading.textContent = title;
    const list = document.createElement("dl");
    fields.forEach(([label, field]) => {
        const term = document.createElement("dt");
        const definition = document.createElement("dd");
        const value = values?.[field];
        term.textContent = label;
        definition.textContent = typeof value === "boolean"
            ? (value ? "正常" : "異常")
            : (value === undefined || value === null || value === "" ? "-" : value);
        list.append(term, definition);
    });
    group.append(heading, list);
    return group;
}

function updateDataViews(options = {}) {
    filteredRows = filterRows(tableRows);
    sortedRows = sortedFilteredRows();
    clampPage(options.preservePage);
    pagedRows = pageRows(sortedRows);
    chartRows = sortRowsByField(filteredRows, "datetime", "asc");

    renderTable();
    renderPagination();

    if (!chartPanel.hidden) {
        drawAllCharts();
    }

    if (!chartModal.hidden) {
        drawModalChart(chartModal.dataset.metric);
    }
}

function renderSummary(payload) {
    if (!sensorSummary) {
        return;
    }

    sensorSummary.textContent = `${payload.csv_path} / ${payload.row_count} 件`;
}

function renderTable() {
    if (!table || !tableHeadRow || !tableBody) {
        return;
    }

    const tableFields = fieldnames.filter((field) => !detailOnlyFields.has(field));
    const expandedRowKeys = new Set(
        [...tableBody.querySelectorAll("tr[data-sensor-row-key] details[open]")]
            .map((details) => details.closest("tr")?.dataset.sensorRowKey)
            .filter(Boolean),
    );
    tableHeadRow.replaceChildren(
        ...tableFields.map((field) => createHeaderCell(field)),
        createDetailsHeaderCell(),
    );

    if (filteredRows.length === 0) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.className = "no-results";
        td.colSpan = Math.max(tableFields.length + 1, 1);
        td.textContent = "条件に一致するデータがありません";
        tr.appendChild(td);
        tableBody.replaceChildren(tr);
        return;
    }

    tableBody.replaceChildren(...pagedRows.map((row) => {
        const tr = document.createElement("tr");
        const rowKey = sensorRowKey(row);
        tr.dataset.sensorRowKey = rowKey;

        tableFields.forEach((field) => {
            const td = document.createElement("td");
            td.textContent = row[field] || "";
            tr.appendChild(td);
        });

        tr.appendChild(createSensorDetailsCell(row, expandedRowKeys.has(rowKey)));

        return tr;
    }));
}

function createDetailsHeaderCell() {
    const th = document.createElement("th");
    th.className = "sensor-detail-heading";
    th.textContent = "詳細";
    return th;
}

function sensorRowKey(row) {
    return [row.client_id, row.datetime, row.session_id, row.sequence].join("\u001f");
}

function createSensorDetailsCell(row, detailsOpen) {
    const td = document.createElement("td");
    td.className = "sensor-detail-cell";
    const details = document.createElement("details");
    details.open = detailsOpen;
    const summary = document.createElement("summary");
    summary.textContent = "表示";
    const list = document.createElement("dl");
    list.className = "sensor-row-detail-list";
    [["セッションID", row.session_id], ["送信番号", row.sequence]].forEach(([label, value]) => {
        const term = document.createElement("dt");
        const definition = document.createElement("dd");
        term.textContent = label;
        definition.textContent = value === undefined || value === null || value === "" ? "-" : value;
        list.append(term, definition);
    });
    details.append(summary, list);
    td.appendChild(details);
    return td;
}

function createHeaderCell(field) {
    const th = document.createElement("th");
    const button = document.createElement("button");
    const indicator = document.createElement("span");
    const isSorted = sortState.field === field;

    th.dataset.field = field;
    th.setAttribute("aria-sort", sortAriaValue(field));

    button.type = "button";
    button.className = "sort-button";
    button.dataset.sortField = field;
    button.addEventListener("click", () => updateSort(field));

    indicator.className = "sort-indicator";
    indicator.textContent = isSorted ? (sortState.direction === "asc" ? "▲" : "▼") : "";
    indicator.setAttribute("aria-hidden", "true");

    button.append(labelForField(field), indicator);
    th.appendChild(button);

    return th;
}

function updateSort(field) {
    if (sortState.field === field) {
        sortState = {
            field,
            direction: sortState.direction === "asc" ? "desc" : "asc",
        };
    } else {
        sortState = { field, direction: "asc" };
    }

    paginationState.page = 1;
    updateDataViews();
}

function filterRows(rows) {
    return rows.filter((row) => (
        textFields.every((field) => matchesTextFilter(row, field))
        && matchesDatetimeFilter(row)
        && numericFields.every((field) => matchesNumericFilter(row, field))
    ));
}

function matchesTextFilter(row, field) {
    const value = filterValue(field).trim();

    if (!value) {
        return true;
    }

    const rowValue = String(row[field] || "").toLowerCase();
    const query = value.toLowerCase();
    const op = filterOp(field);

    if (op === "equals") {
        return rowValue === query;
    }

    return rowValue.includes(query);
}

function matchesDatetimeFilter(row) {
    const rowTime = parseDatetime(row.datetime);
    const min = datetimeInputValue("datetime", "min");
    const max = datetimeInputValue("datetime", "max");

    if (!Number.isFinite(rowTime)) {
        return !min && !max;
    }
    if (min && rowTime < min) {
        return false;
    }
    if (max && rowTime > max) {
        return false;
    }

    return true;
}

function matchesNumericFilter(row, field) {
    const op = filterOp(field);
    const rowValue = Number.parseFloat(row[field]);

    if (op === "equals") {
        const expected = numericInputValue(field, "value");
        return expected === null || (Number.isFinite(rowValue) && rowValue === expected);
    }

    const min = numericInputValue(field, "min");
    const max = numericInputValue(field, "max");

    if (min === null && max === null) {
        return true;
    }
    if (!Number.isFinite(rowValue)) {
        return false;
    }
    if (min !== null && rowValue < min) {
        return false;
    }
    if (max !== null && rowValue > max) {
        return false;
    }

    return true;
}

function filterOp(field) {
    const control = document.querySelector(`[data-filter-op="${field}"]`);
    return control ? control.value : "";
}

function filterValue(field) {
    const control = document.querySelector(`[data-filter-value="${field}"]`);
    return control ? control.value : "";
}

function numericInputValue(field, type) {
    const control = document.querySelector(`[data-filter-${type}="${field}"]`);

    if (!control || control.hidden || control.value === "") {
        return null;
    }

    const value = Number.parseFloat(control.value);
    return Number.isFinite(value) ? value : null;
}

function datetimeInputValue(field, type) {
    const control = document.querySelector(`[data-filter-${type}="${field}"]`);

    if (!control || control.value === "") {
        return null;
    }

    const value = new Date(control.value).getTime();
    return Number.isNaN(value) ? null : value;
}

function sortedFilteredRows() {
    if (!sortState.field) {
        return [...filteredRows];
    }

    return sortRowsByField(filteredRows, sortState.field, sortState.direction);
}

function sortRowsByField(rows, field, direction) {
    const multiplier = direction === "asc" ? 1 : -1;

    return [...rows].sort((a, b) => {
        const aEmpty = isEmptyValue(a[field]);
        const bEmpty = isEmptyValue(b[field]);

        if (aEmpty && bEmpty) {
            return 0;
        }
        if (aEmpty) {
            return 1;
        }
        if (bEmpty) {
            return -1;
        }

        return compareValues(a[field], b[field], field) * multiplier;
    });
}

function compareValues(a, b, field) {
    if (field === "datetime") {
        const aTime = parseDatetime(a);
        const bTime = parseDatetime(b);

        if (Number.isFinite(aTime) && Number.isFinite(bTime)) {
            return aTime - bTime;
        }
    }

    const aNumber = Number.parseFloat(a);
    const bNumber = Number.parseFloat(b);

    if (Number.isFinite(aNumber) && Number.isFinite(bNumber)) {
        return aNumber - bNumber;
    }

    return String(a).localeCompare(String(b), "ja", {
        numeric: true,
        sensitivity: "base",
    });
}

function pageRows(rows) {
    const start = (paginationState.page - 1) * paginationState.pageSize;
    return rows.slice(start, start + paginationState.pageSize);
}

function totalPages() {
    return Math.max(1, Math.ceil(filteredRows.length / paginationState.pageSize));
}

function clampPage(preservePage = false) {
    const maxPage = totalPages();

    if (!preservePage) {
        paginationState.page = 1;
        return;
    }

    paginationState.page = Math.min(Math.max(paginationState.page, 1), maxPage);
}

function renderPagination() {
    const total = filteredRows.length;
    const maxPage = totalPages();
    const start = total === 0 ? 0 : (paginationState.page - 1) * paginationState.pageSize + 1;
    const end = total === 0 ? 0 : Math.min(start + paginationState.pageSize - 1, total);

    pageSummaries.forEach((summary) => {
        summary.textContent = `${start}-${end} / ${total} 件`;
    });
    pageCurrentLabels.forEach((label) => {
        label.textContent = `${paginationState.page} / ${maxPage}`;
    });
    pageSizeSelects.forEach((select) => {
        const pageSize = String(paginationState.pageSize);
        select.value = [...select.options].some((option) => option.value === pageSize) ? pageSize : "custom";
    });
    pageSizeCustomInputs.forEach((input) => {
        input.value = String(paginationState.pageSize);
        input.hidden = !isCustomPageSize();
    });
    prevPageButtons.forEach((button) => {
        button.disabled = paginationState.page <= 1;
    });
    nextPageButtons.forEach((button) => {
        button.disabled = paginationState.page >= maxPage;
    });
}

function clearFilters() {
    filterControls.forEach((control) => {
        if (control.matches("select")) {
            control.selectedIndex = 0;
        } else {
            control.value = "";
        }
    });
    syncNumericFilterInputs();
    paginationState.page = 1;
    updateDataViews();
}

function syncNumericFilterInputs() {
    numericFields.forEach((field) => {
        const isEquals = filterOp(field) === "equals";
        const min = document.querySelector(`[data-filter-min="${field}"]`);
        const max = document.querySelector(`[data-filter-max="${field}"]`);
        const value = document.querySelector(`[data-filter-value="${field}"]`);

        min.hidden = isEquals;
        max.hidden = isEquals;
        value.hidden = !isEquals;
    });
}

function isEmptyValue(value) {
    return value === undefined || value === null || value === "";
}

function parseDatetime(value) {
    const normalized = String(value).replace(/\s+[A-Za-z]+\s+/, " ");
    const match = normalized.match(/^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})$/);

    if (!match) {
        const parsed = Date.parse(normalized);
        return Number.isNaN(parsed) ? NaN : parsed;
    }

    const [, year, month, day, hour, minute, second] = match.map(Number);
    return new Date(year, month - 1, day, hour, minute, second).getTime();
}

function sortAriaValue(field) {
    if (sortState.field !== field) {
        return "none";
    }

    return sortState.direction === "asc" ? "ascending" : "descending";
}

function labelForField(field) {
    return fieldLabels[field] || fallbackFieldLabels[field] || field;
}

function renderEmptyState() {
    const hasRows = tableRows.length > 0;

    toolbar.hidden = false;
    filterPanel.hidden = !hasRows || !["table", "graph"].includes(currentView());
    paginationBars.forEach((paginationBar) => {
        paginationBar.hidden = !hasRows || currentView() !== "table";
    });
    emptyState.hidden = hasRows || currentView() !== "table";

    if (!hasRows) {
        chartPanel.hidden = true;
        tablePanel.hidden = true;
    }
}

function drawAllCharts() {
    const limitedRows = limitRows(chartRows, chartLimit);
    chartCanvases.forEach((canvas) => {
        const metric = canvas.dataset.chartMetric;
        drawChart(canvas, metric, limitedRows, chartAxisRange(metric));
    });
}

function modalRowsForMetric(metric) {
    const state = modalFilterState[metric] || defaultModalFilterState();
    const rows = chartRows.filter((row) => (
        textFields.every((field) => matchesModalTextFilter(row, field, state))
        && matchesModalDatetimeFilter(row, state)
        && matchesModalMetricFilter(row, metric, state)
    ));

    return limitRows(rows, state.limit);
}

function matchesModalTextFilter(row, field, state) {
    const filter = state.text[field];
    const value = filter.value.trim();

    if (!value) {
        return true;
    }

    const rowValue = String(row[field] || "").toLowerCase();
    const query = value.toLowerCase();

    if (filter.op === "equals") {
        return rowValue === query;
    }

    return rowValue.includes(query);
}

function limitRows(rows, limit) {
    if (limit === "all") {
        return rows;
    }

    const count = Number.parseInt(limit, 10);
    if (!Number.isFinite(count)) {
        return rows;
    }
    return rows.slice(-count);
}

function chartAxisRange(metric) {
    if (filterOp(metric) !== "range") {
        return null;
    }

    return axisRangeFromValues(
        numericInputValue(metric, "min"),
        numericInputValue(metric, "max"),
    );
}

function modalAxisRange(metric) {
    const state = modalFilterState[metric] || defaultModalFilterState();

    if (state.op !== "range") {
        return null;
    }

    return axisRangeFromValues(
        parseOptionalNumber(state.min),
        parseOptionalNumber(state.max),
    );
}

function axisRangeFromValues(min, max) {
    if (min === null && max === null) {
        return null;
    }

    if (min !== null && max !== null && min > max) {
        return { min: max, max: min };
    }

    return { min, max };
}

function matchesModalDatetimeFilter(row, state) {
    const rowTime = parseDatetime(row.datetime);
    const min = state.datetimeMin ? new Date(state.datetimeMin).getTime() : null;
    const max = state.datetimeMax ? new Date(state.datetimeMax).getTime() : null;

    if (!Number.isFinite(rowTime)) {
        return !min && !max;
    }
    if (min && rowTime < min) {
        return false;
    }
    if (max && rowTime > max) {
        return false;
    }

    return true;
}

function matchesModalMetricFilter(row, metric, state) {
    const rowValue = Number.parseFloat(row[metric]);

    if (state.op === "equals") {
        const expected = parseOptionalNumber(state.value);
        return expected === null || (Number.isFinite(rowValue) && rowValue === expected);
    }

    const min = parseOptionalNumber(state.min);
    const max = parseOptionalNumber(state.max);

    if (min === null && max === null) {
        return true;
    }
    if (!Number.isFinite(rowValue)) {
        return false;
    }
    if (min !== null && rowValue < min) {
        return false;
    }
    if (max !== null && rowValue > max) {
        return false;
    }

    return true;
}

function parseOptionalNumber(value) {
    if (value === "") {
        return null;
    }

    const number = Number.parseFloat(value);
    return Number.isFinite(number) ? number : null;
}

function drawChart(canvas, metric, rows, axisRange = null) {
    if (!canvas) {
        return;
    }

    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();

    canvas.width = Math.floor(rect.width * dpr);
    canvas.height = Math.floor(rect.height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const width = rect.width;
    const height = rect.height;
    const padding = { top: 28, right: 28, bottom: 54, left: 72 };
    const plotWidth = width - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;
    const points = rows
        .map((row) => ({
            datetime: row.datetime || "",
            value: Number.parseFloat(row[metric]),
        }))
        .filter((point) => Number.isFinite(point.value));

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);

    if (points.length === 0) {
        ctx.fillStyle = "#667085";
        ctx.font = "14px Arial";
        ctx.fillText("グラフデータがありません", padding.left, padding.top + 16);
        return;
    }

    const values = points.map((point) => point.value);
    let min = Math.min(...values);
    let max = Math.max(...values);

    if (axisRange) {
        min = axisRange.min ?? min;
        max = axisRange.max ?? max;
    }

    if (min === max) {
        min -= 1;
        max += 1;
    }

    const range = max - min;
    const yMin = axisRange ? min : min - range * 0.08;
    const yMax = axisRange ? max : max + range * 0.08;
    const yRange = yMax - yMin;
    const color = metricColors[metric] || "#2563eb";
    const average = values.reduce((sum, value) => sum + value, 0) / values.length;

    ctx.strokeStyle = "#d7dee8";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padding.left, padding.top);
    ctx.lineTo(padding.left, padding.top + plotHeight);
    ctx.lineTo(padding.left + plotWidth, padding.top + plotHeight);
    ctx.stroke();

    ctx.fillStyle = "#667085";
    ctx.font = "12px Arial";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";

    for (let i = 0; i <= 4; i += 1) {
        const y = padding.top + (plotHeight / 4) * i;
        const value = yMax - (yRange / 4) * i;

        ctx.strokeStyle = "#edf1f5";
        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(padding.left + plotWidth, y);
        ctx.stroke();

        ctx.fillText(formatValue(value), padding.left - 10, y);
    }

    const xFor = (index) => {
        if (points.length === 1) {
            return padding.left + plotWidth / 2;
        }
        return padding.left + (plotWidth * index) / (points.length - 1);
    };
    const yFor = (value) => padding.top + plotHeight - ((value - yMin) / yRange) * plotHeight;
    const averageY = yFor(average);

    ctx.save();
    ctx.strokeStyle = "#111827";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([6, 5]);
    ctx.beginPath();
    ctx.moveTo(padding.left, averageY);
    ctx.lineTo(padding.left + plotWidth, averageY);
    ctx.stroke();
    ctx.restore();

    ctx.fillStyle = "#111827";
    ctx.font = "12px Arial";
    ctx.textAlign = "right";
    ctx.textBaseline = "bottom";
    ctx.fillText(`平均 ${formatValue(average)}`, padding.left + plotWidth - 2, averageY - 4);

    ctx.strokeStyle = color;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    points.forEach((point, index) => {
        const x = xFor(index);
        const y = yFor(point.value);

        if (index === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    });
    ctx.stroke();

    ctx.fillStyle = color;
    points.forEach((point, index) => {
        const x = xFor(index);
        const y = yFor(point.value);

        ctx.beginPath();
        ctx.arc(x, y, 3.5, 0, Math.PI * 2);
        ctx.fill();
    });

    drawXAxisLabels(ctx, points, padding, plotWidth, plotHeight, xFor);

    ctx.fillStyle = "#1f2933";
    ctx.font = "700 15px Arial";
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    ctx.fillText(metricLabels[metric] || metric, padding.left, 8);
}

function openChartModal(metric) {
    chartModal.dataset.metric = metric;
    chartModalTitle.textContent = `${metricLabels[metric] || metric}グラフ`;
    loadModalFilterState(metric);
    chartModal.hidden = false;
    document.body.classList.add("modal-open");
    requestAnimationFrame(() => drawModalChart(metric));
}

function closeChartModal() {
    chartModal.hidden = true;
    chartModal.dataset.metric = "";
    document.body.classList.remove("modal-open");
}

function drawModalChart(metric) {
    if (!metric) {
        return;
    }

    drawChart(chartModalCanvas, metric, modalRowsForMetric(metric), modalAxisRange(metric));
}

function downloadChart(metric, canvas) {
    if (!canvas) {
        return;
    }

    const filename = chartFilename(metric);

    if (canvas.toBlob) {
        canvas.toBlob((blob) => {
            if (!blob) {
                downloadDataUrl(canvas.toDataURL("image/png"), filename);
                return;
            }

            const url = URL.createObjectURL(blob);
            downloadDataUrl(url, filename);
            window.setTimeout(() => URL.revokeObjectURL(url), 1000);
        }, "image/png");
        return;
    }

    downloadDataUrl(canvas.toDataURL("image/png"), filename);
}

function downloadDataUrl(url, filename) {
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
}

function chartFilename(metric) {
    const now = new Date();
    const timestamp = [
        now.getFullYear(),
        String(now.getMonth() + 1).padStart(2, "0"),
        String(now.getDate()).padStart(2, "0"),
        "-",
        String(now.getHours()).padStart(2, "0"),
        String(now.getMinutes()).padStart(2, "0"),
        String(now.getSeconds()).padStart(2, "0"),
    ].join("");

    return `sensor-${metricFileNames[metric] || metric}-${timestamp}.png`;
}

function defaultModalFilterState() {
    return {
        text: {
            client_id: { op: "contains", value: "" },
            region: { op: "contains", value: "" },
        },
        datetimeMin: "",
        datetimeMax: "",
        op: "range",
        min: "",
        max: "",
        value: "",
        limit: chartLimit,
    };
}

function loadModalFilterState(metric) {
    const state = modalFilterState[metric] || defaultModalFilterState();
    const step = metric === "co2" ? "1" : "0.1";

    textFields.forEach((field) => {
        document.querySelector(`[data-modal-text-op="${field}"]`).value = state.text[field].op;
        document.querySelector(`[data-modal-text-value="${field}"]`).value = state.text[field].value;
    });
    modalMetricLabel.textContent = metricLabels[metric] || metric;
    modalDatetimeMin.value = state.datetimeMin;
    modalDatetimeMax.value = state.datetimeMax;
    modalFilterOp.value = state.op;
    modalMetricMin.value = state.min;
    modalMetricMax.value = state.max;
    modalMetricValue.value = state.value;
    modalChartLimitSelect.value = String(state.limit || chartLimit);
    modalMetricMin.step = step;
    modalMetricMax.step = step;
    modalMetricValue.step = step;
    syncModalFilterInputs();
}

function saveModalFilterState(metric) {
    if (!metric) {
        return;
    }

    modalFilterState[metric] = {
        text: {
            client_id: {
                op: document.querySelector('[data-modal-text-op="client_id"]').value,
                value: document.querySelector('[data-modal-text-value="client_id"]').value,
            },
            region: {
                op: document.querySelector('[data-modal-text-op="region"]').value,
                value: document.querySelector('[data-modal-text-value="region"]').value,
            },
        },
        datetimeMin: modalDatetimeMin.value,
        datetimeMax: modalDatetimeMax.value,
        op: modalFilterOp.value,
        min: modalMetricMin.value,
        max: modalMetricMax.value,
        value: modalMetricValue.value,
        limit: modalChartLimitSelect.value,
    };
}

function syncModalFilterInputs() {
    const isEquals = modalFilterOp.value === "equals";

    modalMetricMin.hidden = isEquals;
    modalMetricMax.hidden = isEquals;
    modalMetricValue.hidden = !isEquals;
}

function updateModalFilter() {
    const metric = chartModal.dataset.metric;

    syncModalFilterInputs();
    saveModalFilterState(metric);
    drawModalChart(metric);
}

function clearModalFilter() {
    const metric = chartModal.dataset.metric;

    modalFilterState[metric] = defaultModalFilterState();
    loadModalFilterState(metric);
    drawModalChart(metric);
}

function drawXAxisLabels(ctx, points, padding, plotWidth, plotHeight, xFor) {
    const indexes = points.length <= 4
        ? points.map((_, index) => index)
        : [0, Math.floor((points.length - 1) / 2), points.length - 1];

    ctx.fillStyle = "#667085";
    ctx.font = "12px Arial";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";

    indexes.forEach((index) => {
        const x = xFor(index);
        const label = compactDatetime(points[index].datetime);
        ctx.fillText(label, x, padding.top + plotHeight + 14);
    });
}

function compactDatetime(value) {
    return value.replace(/^\d{4}-/, "").replace(/\s+[A-Za-z]+\s+/, " ").replace(" ", "\n");
}

function formatValue(value) {
    if (Math.abs(value) >= 100) {
        return value.toFixed(0);
    }
    return value.toFixed(1);
}

syncNumericFilterInputs();
renderTextSuggestions();
updateDataViews({ preservePage: true });
connectHealthStream();

viewButtons.forEach((button) => {
    button.addEventListener("click", () => {
        setView(button.dataset.viewButton);
        if (button.dataset.viewButton === "health") {
            refreshHealthData();
        }
    });
});

filterControls.forEach((control) => {
    control.addEventListener("input", () => {
        paginationState.page = 1;
        updateDataViews();
    });
    control.addEventListener("change", () => {
        syncNumericFilterInputs();
        paginationState.page = 1;
        updateDataViews();
    });
});

numericFilterOps.forEach((control) => {
    control.addEventListener("change", syncNumericFilterInputs);
});

clearFiltersButton.addEventListener("click", clearFilters);
healthFilterControls.forEach((control) => control.addEventListener("input", renderHealth));
clearHealthFiltersButton.addEventListener("click", clearHealthFilters);
refreshButton.addEventListener("click", refreshDashboardData);
pageSizeSelects.forEach((select) => {
    select.addEventListener("change", () => {
        if (select.value === "custom") {
            pageSizeSelects.forEach((pageSizeSelect) => {
                pageSizeSelect.value = "custom";
            });
            pageSizeCustomInputs.forEach((input) => {
                input.hidden = false;
                input.value = String(paginationState.pageSize);
            });
            select.closest(".page-size-select").querySelector("[data-page-size-custom]").focus();
            return;
        }

        paginationState.pageSize = Number.parseInt(select.value, 10);
        paginationState.page = 1;
        updateDataViews();
    });
});
pageSizeCustomInputs.forEach((input) => {
    input.addEventListener("change", () => {
        const pageSize = Number.parseInt(input.value, 10);

        if (!Number.isFinite(pageSize) || pageSize < 1) {
            input.value = String(paginationState.pageSize);
            return;
        }

        paginationState.pageSize = pageSize;
        paginationState.page = 1;
        updateDataViews();
    });
});

function isCustomPageSize() {
    const pageSize = String(paginationState.pageSize);
    return !["25", "50", "100"].includes(pageSize);
}
chartLimitSelect.addEventListener("change", () => {
    chartLimit = chartLimitSelect.value;
    drawAllCharts();
});
prevPageButtons.forEach((button) => {
    button.addEventListener("click", () => {
        paginationState.page -= 1;
        updateDataViews({ preservePage: true });
    });
});
nextPageButtons.forEach((button) => {
    button.addEventListener("click", () => {
        paginationState.page += 1;
        updateDataViews({ preservePage: true });
    });
});
chartPanes.forEach((pane) => {
    pane.addEventListener("click", () => openChartModal(pane.dataset.graphPane));
});
chartDownloadButtons.forEach((button) => {
    button.addEventListener("click", (event) => {
        event.stopPropagation();
        const metric = button.dataset.graphDownload;
        const canvas = document.querySelector(`[data-chart-metric="${metric}"]`);
        downloadChart(metric, canvas);
    });
});
chartModalCloseButtons.forEach((button) => {
    button.addEventListener("click", closeChartModal);
});
chartModalDownloadButton.addEventListener("click", () => {
    downloadChart(chartModal.dataset.metric, chartModalCanvas);
});
modalFilterControls.forEach((control) => {
    control.addEventListener("input", updateModalFilter);
    control.addEventListener("change", updateModalFilter);
});
modalChartLimitSelect.addEventListener("change", updateModalFilter);
modalFilterClearButton.addEventListener("click", clearModalFilter);
window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !chartModal.hidden) {
        closeChartModal();
    }
});
window.addEventListener("resize", () => {
    if (!chartPanel.hidden) {
        drawAllCharts();
    }

    if (!chartModal.hidden) {
        drawModalChart(chartModal.dataset.metric);
    }
});
