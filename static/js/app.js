/*
 * Line-item tables (PO, goods receipt, quotation …).
 *
 * Markup:
 *   <table data-formset="lines" data-lookup="materials" data-lookup-field="material-select">
 *   <template id="lines-empty">…one row with __prefix__…</template>
 *   <button data-add-row="lines">
 * A <script type="application/json" id="materials"> gives rate/tax/unit per id,
 * used to fill the row when an item is picked.
 */
(function () {
  "use strict";

  function lookup(name) {
    var el = document.getElementById(name);
    if (!el) return {};
    try { return JSON.parse(el.textContent); } catch (e) { return {}; }
  }

  function num(v) { var n = parseFloat(v); return isNaN(n) ? 0 : n; }

  function money(n) {
    return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function rowTotal(row) {
    var q = row.querySelector("input.quantity"), r = row.querySelector("input.rate");
    var out = row.querySelector("[data-amount]");
    if (!q || !r || !out) return 0;
    var amount = num(q.value) * num(r.value);
    out.textContent = amount ? money(amount) : "";
    return amount;
  }

  function tableTotal(table) {
    var sum = 0;
    table.querySelectorAll("tbody tr").forEach(function (row) {
      var del = row.querySelector("input[name$='-DELETE']");
      if (del && del.checked) return;
      sum += rowTotal(row);
    });
    var out = document.querySelector("[data-total-for='" + table.dataset.formset + "']");
    if (out) out.textContent = money(sum);
  }

  function fill(row, data, prefix) {
    function set(cls, val, force) {
      var input = row.querySelector("." + cls) || row.querySelector("[name$='-" + cls + "']");
      if (input && val !== undefined && (force || !input.value || input.value === "0")) input.value = val;
    }
    set("rate", data.rate, true);
    set("tax_rate", data.tax, true);
    set("unit", data.unit, true);
    if (data.name !== undefined) {
      var d = row.querySelector("[name$='-description']");
      if (d && !d.value) d.value = data.name + (data.description ? "\n" + data.description : "");
    }
    var u = row.querySelector("[data-unit]");
    if (u) u.textContent = data.unit || "";
  }

  function wire(table) {
    var data = lookup(table.dataset.lookup);
    var field = table.dataset.lookupField;
    table.addEventListener("change", function (e) {
      if (field && e.target.classList.contains(field)) {
        var row = e.target.closest("tr");
        var item = data[e.target.value];
        if (item) fill(row, item);
      }
      tableTotal(table);
    });
    table.addEventListener("input", function () { tableTotal(table); });
    // show units for rows that are already filled
    if (field) {
      table.querySelectorAll("select." + field).forEach(function (sel) {
        var item = data[sel.value], u = sel.closest("tr").querySelector("[data-unit]");
        if (item && u) u.textContent = item.unit || "";
      });
    }
    tableTotal(table);
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-add-row]");
    if (!btn) return;
    e.preventDefault();
    var prefix = btn.dataset.addRow;
    var total = document.getElementById("id_" + prefix + "-TOTAL_FORMS");
    var tpl = document.getElementById(prefix + "-empty");
    var tbody = document.querySelector("table[data-formset='" + prefix + "'] tbody");
    if (!total || !tpl || !tbody) return;
    var index = parseInt(total.value, 10);
    var html = tpl.innerHTML.replace(/__prefix__/g, index);
    tbody.insertAdjacentHTML("beforeend", html);
    total.value = index + 1;
    var first = tbody.lastElementChild.querySelector("select, input:not([type=hidden])");
    if (first) first.focus();
  });

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("table[data-formset]").forEach(wire);
  });
})();

/*
 * "Share PDF" – hands the real PDF file to the phone's share sheet (WhatsApp, Gmail …).
 * The file is downloaded when the page opens, because iPhones only allow the share
 * sheet to open immediately after a tap (not after waiting for a download).
 */
(function () {
  "use strict";
  var files = new WeakMap();

  function unsupported() {
    var note = document.querySelector("[data-share-unsupported]");
    if (note) note.hidden = false;
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-share-pdf]").forEach(function (btn) {
      if (!navigator.share || !window.File) { unsupported(); return; }
      fetch(btn.dataset.sharePdf, { credentials: "same-origin" })
        .then(function (res) { return res.blob(); })
        .then(function (blob) {
          files.set(btn, new File([blob], btn.dataset.filename || "document.pdf",
                                  { type: blob.type || "application/pdf" }));
        })
        .catch(unsupported);
    });
  });

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-share-pdf]");
    if (!btn) return;
    e.preventDefault();
    var file = files.get(btn);
    if (!file) { if (!navigator.share) unsupported(); else if (btn.dataset.wait) alert(btn.dataset.wait); return; }
    if (navigator.canShare && !navigator.canShare({ files: [file] })) { unsupported(); return; }
    navigator.share({ files: [file], title: btn.dataset.title || "" }).catch(function (err) {
      if (err && err.name !== "AbortError") unsupported();
    });
  });
})();
