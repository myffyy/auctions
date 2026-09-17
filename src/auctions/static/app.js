const $ = (selector) => document.querySelector(selector);
let me;

async function request(path, options = {}) {
  const response = await fetch(path, options);
  if (response.status === 401) return window.location.assign("/login");
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "Не удалось выполнить действие");
  return payload;
}

function showMessage(text, isError = false) {
  const message = $("#message");
  message.textContent = text;
  message.className = isError ? "message error" : "message success";
}

function table(rows, fields) {
  if (!rows.length) return "<p class='empty'>Пока нет данных.</p>";
  const header = fields.map(([_, title]) => `<th>${title}</th>`).join("");
  const body = rows.map((row) => `<tr>${fields.map(([key]) => `<td>${row[key] ?? "—"}</td>`).join("")}</tr>`).join("");
  return `<table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table>`;
}

function form(title, fields, submit) {
  const controls = fields.map(([name, label, type = "text", hint = "", optional = false]) => {
    const required = optional ? "" : "required";
    if (type === "select") {
      const options = hint.map(([value, text]) => `<option value="${value}">${text}</option>`).join("");
      return `<label>${label}<select name="${name}" ${required}>${options}</select></label>`;
    }
    return `<label>${label}<input name="${name}" type="${type}" ${hint} ${required}></label>`;
  }).join("");
  return `<article class="form-card"><h2>${title}</h2><form data-action="${submit}">${controls}<button>Сохранить</button></form></article>`;
}

async function refresh() {
  const [auctions, lots, purchaseRequests, sales] = await Promise.all([request("/web/auctions"), request("/web/lots"), request("/web/purchase-requests"), request("/web/sales")]);
  $("#auctions").innerHTML = table(auctions, [["id", "ID"], ["name", "Название"], ["status", "Статус"]]);
  $("#lots").innerHTML = table(lots, [["id", "ID"], ["name", "Лот"], ["auction_id", "Аукцион"], ["starting_price", "Стартовая цена"], ["status", "Статус"]]);
  const requestFields = [["id", "ID"], ["lot_id", "Лот"], ["buyer_id", "Покупатель"], ["offered_price", "Цена"], ["status", "Статус"]];
  $("#purchase-requests").innerHTML = table(purchaseRequests, requestFields);
  if (me.role === "admin" && purchaseRequests.length) {
    $("#purchase-requests").querySelectorAll("tbody tr").forEach((row, index) => {
      const item = purchaseRequests[index];
      const cell = document.createElement("td");
      if (item.status === "pending") cell.innerHTML = `<button data-review="approve" data-id="${item.id}">Подтвердить</button> <button class="danger" data-review="reject" data-id="${item.id}">Отклонить</button>`;
      row.append(cell);
    });
  }
  $("#sales").innerHTML = table(sales, [["id", "ID"], ["lot_id", "Лот"], ["buyer_id", "Покупатель"], ["final_price", "Цена"]]);
  if (me.role === "admin") {
    const [revenues, accounts, sellers, buyers] = await Promise.all([request("/web/revenues"), request("/web/admin/accounts"), request("/web/admin/sellers"), request("/web/admin/buyers")]);
    $("#revenues-card").hidden = false;
    $("#participants-card").hidden = false;
    $("#revenues").innerHTML = table(revenues, [["id", "ID"], ["sale_id", "Продажа"], ["amount", "Сумма"]]);
    $("#participants").innerHTML = `<h3>Пользователи</h3>${table(accounts, [["id", "ID"], ["full_name", "ФИО"], ["username", "Логин"], ["role", "Роль"], ["profile", "Профиль"]])}<h3>Продавцы</h3>${table(sellers, [["id", "ID"], ["name", "ФИО"]])}<h3>Покупатели</h3>${table(buyers, [["id", "ID"], ["name", "ФИО"]])}`;
  }
}

function renderActions() {
  if (me.role === "admin") {
    $("#actions").innerHTML = form("Учётная запись", [["last_name", "Фамилия"], ["first_name", "Имя"], ["middle_name", "Отчество"], ["username", "Логин"], ["password", "Пароль (от 8 символов)", "password", "minlength='8'"], ["role", "Роль", "select", [["user", "Пользователь"], ["admin", "Администратор"]]]], "account") + form("Новый участник аукциона", [["account_id", "ID существующего пользователя", "number"], ["profile", "Профиль", "select", [["seller", "Продавец"], ["buyer", "Покупатель"]]]], "participant") + form("Новый аукцион", [["name", "Название"], ["starts_at", "Начало", "datetime-local"], ["ends_at", "Окончание", "datetime-local"]], "auction");
  } else if (me.profile === "seller") {
    $("#actions").innerHTML = form("Выставить лот", [["auction_id", "ID аукциона", "number"], ["name", "Название"], ["description", "Описание"], ["starting_price", "Стартовая цена", "number", "step='0.01' min='0.01'"]], "lot");
  } else if (me.profile === "buyer") {
    $("#actions").innerHTML = form("Заявка на покупку", [["lot_id", "ID лота", "number"], ["offered_price", "Предлагаемая цена", "number", "step='0.01' min='0.01'"]], "purchase-request");
  } else {
    $("#actions").innerHTML = "<article><h2>Профиль ещё не назначен</h2><p>Администратор должен зарегистрировать пользователя как продавца или покупателя.</p></article>";
  }
}

$("#actions").addEventListener("submit", async (event) => {
  if (!event.target.matches("form")) return;
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  Object.keys(data).forEach((key) => { if (data[key] === "") delete data[key]; });
  const action = event.target.dataset.action;
  const endpoints = {participant: "/web/admin/participants", auction: "/web/admin/auctions", account: "/web/admin/accounts", lot: "/web/seller/lots", "purchase-request": "/web/buyer/purchase-requests"};
  if (action === "auction") { data.starts_at = new Date(data.starts_at).toISOString(); data.ends_at = new Date(data.ends_at).toISOString(); }
  if (["lot", "purchase-request", "participant"].includes(action)) for (const key of ["lot_id", "auction_id", "account_id"]) if (data[key]) data[key] = Number(data[key]);
  if (action === "lot") data.seller_id = 1;
  try { await request(endpoints[action], {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)}); event.target.reset(); showMessage("Изменения сохранены"); await refresh(); }
  catch (error) { showMessage(error.message, true); }
});

$("#purchase-requests").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-review]");
  if (!button) return;
  try {
    await request(`/web/admin/purchase-requests/${button.dataset.id}/${button.dataset.review}`, {method: "POST"});
    showMessage(button.dataset.review === "approve" ? "Продажа подтверждена" : "Заявка отклонена");
    await refresh();
  } catch (error) { showMessage(error.message, true); }
});

$("#logout").addEventListener("click", async () => { await request("/auth/logout", {method: "POST"}); window.location.assign("/login"); });

(async () => { me = await request("/auth/me"); $("#user").textContent = `${me.full_name} · ${me.username} · ${me.role}`; renderActions(); refresh(); })().catch((error) => showMessage(error.message, true));
