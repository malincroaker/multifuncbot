"use strict";
const tg = window.Telegram?.WebApp;
const $ = (selector) => document.querySelector(selector);
const state = {
  language: localStorage.getItem("shop-language") || "ru",
  products: [],
  cart: { lines: [], count: 0, subtotal: 0 },
  category: "all",
  busy: false,
  checkoutKey: null,
  ready: false,
};
if (!["ru", "en"].includes(state.language)) state.language = "ru";
const tr = (ru, en) => (state.language === "ru" ? ru : en);
const money = (value) =>
  new Intl.NumberFormat(state.language === "ru" ? "ru-RU" : "en-US", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0,
  }).format(value / 100);
const element = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};
const button = (text, className, handler) => {
  const node = element("button", className, text);
  node.type = "button";
  node.addEventListener("click", handler);
  return node;
};
const statusText = (status) =>
  ({
    awaiting_payment: tr("Ожидает демо-оплаты", "Awaiting demo payment"),
    paid: tr("Демо-оплата успешна", "Demo payment successful"),
    payment_failed: tr("Демо-оплата отклонена", "Demo payment failed"),
    cancelled: tr("Заказ отменён", "Order cancelled"),
  })[status] || status;

async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    "X-Multifuncbot": "1",
    ...options.headers,
  };
  if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
  const response = await fetch(`/api${path}`, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  const body = await response.json();
  if (!response.ok) {
    const detail = body.detail;
    throw new Error(
      typeof detail === "object" && !Array.isArray(detail)
        ? detail[state.language]
        : typeof detail === "string"
          ? detail
          : tr("Проверьте введённые данные.", "Check your input."),
    );
  }
  return body;
}
function report(error) {
  const banner = $("#error-banner");
  banner.textContent =
    error.message || tr("Не удалось загрузить данные.", "Unable to load data.");
  banner.hidden = false;
}
function clearError() {
  $("#error-banner").hidden = true;
}
function toast(text) {
  const node = $("#toast");
  node.textContent = text;
  node.hidden = false;
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => {
    node.hidden = true;
  }, 1800);
}
function openDialog(title) {
  $("#dialog-title").textContent = title;
  $("#dialog-body").replaceChildren();
  if (!$("#shop-dialog").open) $("#shop-dialog").showModal();
  return $("#dialog-body");
}
function closeDialog() {
  $("#shop-dialog").close();
}
function quantityFor(id) {
  return state.cart.lines.find((line) => line.id === id)?.quantity || 0;
}

function renderCopy() {
  document.documentElement.lang = state.language;
  document.title = tr("Место · Демо-магазин", "Mesto · Demo shop");
  $("#demo-strip").textContent = tr(
    "Демо-магазин · Настоящие деньги не списываются",
    "Demo shop · No real money is charged",
  );
  $("#brand-name").textContent = tr("место", "mesto");
  $(".brand").setAttribute("aria-label", tr("Место, главная", "Mesto, home"));
  $("#hero-product img").alt = tr(
    "Блокнот в мягкой зелёной обложке",
    "A notebook with a soft green cover",
  );
  $("#categories").setAttribute("aria-label", tr("Категории", "Categories"));
  $("#orders-button").textContent = tr("Заказы", "Orders");
  $("#language-button").textContent = state.language === "ru" ? "EN" : "RU";
  $("#hero-label").textContent = tr(
    "Для рабочего стола и не только",
    "For your desk, and beyond",
  );
  $("#hero-title").replaceChildren(
    document.createTextNode(tr("Место для", "Space for")),
    document.createElement("br"),
    document.createTextNode(tr("хороших идей.", "good ideas.")),
  );
  $("#hero-description").textContent = tr(
    "Блокноты, любимая кружка и маленькие вещи, с которых начинается большой план.",
    "Notebooks, a favourite mug, and the little things that start a bigger plan.",
  );
  $("#hero-link").textContent = tr("Найти своё →", "Find your thing →");
  $("#hero-caption").replaceChildren(
    document.createTextNode(tr("Блокнот «Точка»", "Dot notebook")),
    element("strong", "", `${money(89000)} ↗`),
  );
  $("#hero-product").setAttribute(
    "aria-label",
    tr("Открыть блокнот Точка", "View Dot notebook"),
  );
  $("#catalog-title").textContent = tr(
    "Хорошие вещи на каждый день",
    "Good things for everyday",
  );
  $("#search").placeholder = tr("Найти вещь", "Find something");
  $("#search").setAttribute(
    "aria-label",
    tr("Поиск по каталогу", "Search catalogue"),
  );
  $("#delivery-title").textContent = tr(
    "Собрали. Проверили. Отправили.",
    "Picked. Checked. On its way.",
  );
  $("#delivery-copy").textContent = tr(
    "Демо-доставка — 300 ₽, от 3 000 ₽ бесплатно. Самовывоз — бесплатно. Все товары и заказы вымышленные.",
    "Demo delivery is ₽300, free from ₽3,000. Free pickup. All products and orders are fictional.",
  );
  $("#footer-brand").textContent = tr(
    "место · Демо от Multifuncbot",
    "mesto · A Multifuncbot demo",
  );
  $("#footer-note").textContent = tr(
    "Небольшие вещи. Большие планы.",
    "Little things. Bigger plans.",
  );
  $("#orders-title").textContent = tr("Мои заказы", "My orders");
  $("#back-catalog").textContent = tr("К каталогу →", "Back to catalogue →");
  $("#close-dialog").setAttribute("aria-label", tr("Закрыть", "Close"));
  renderCategories();
  renderProducts();
  renderCartBadge();
}
function renderCategories() {
  $("#categories").replaceChildren(
    ...[
      ["all", "Всё", "All"],
      ["paper", "Бумага", "Paper"],
      ["tools", "Инструменты", "Tools"],
      ["everyday", "На каждый день", "Everyday"],
    ].map(([id, ru, en]) => {
      const node = button(tr(ru, en), "category", () => {
        state.category = id;
        renderCategories();
        renderProducts();
      });
      node.setAttribute("aria-pressed", String(state.category === id));
      return node;
    }),
  );
}
function quantityControl(product) {
  const quantity = quantityFor(product.id);
  if (!quantity)
    return button(tr("В корзину +", "Add +"), "add-button", () =>
      updateQuantity(product.id, 1),
    );
  const group = element("div", "quantity");
  const minus = button("−", "", () => updateQuantity(product.id, quantity - 1));
  minus.setAttribute(
    "aria-label",
    tr(`Уменьшить: ${product.title.ru}`, `Remove one ${product.title.en}`),
  );
  const plus = button("+", "", () => updateQuantity(product.id, quantity + 1));
  plus.setAttribute(
    "aria-label",
    tr(`Добавить: ${product.title.ru}`, `Add one ${product.title.en}`),
  );
  plus.disabled = quantity >= 20;
  group.append(minus, element("span", "", String(quantity)), plus);
  return group;
}
function renderProducts() {
  const search = $("#search").value.trim().toLocaleLowerCase();
  const products = state.products.filter(
    (product) =>
      (state.category === "all" || product.category === state.category) &&
      `${product.title[state.language]} ${product.description[state.language]}`
        .toLocaleLowerCase()
        .includes(search),
  );
  $("#product-count").textContent = tr(
    `${products.length} из ${state.products.length}`,
    `${products.length} of ${state.products.length}`,
  );
  $("#products").replaceChildren(
    ...products.map((product) => {
      const card = element("article", "product");
      const imageButton = button("", `product-image ${product.color}`, () =>
        showProduct(product),
      );
      imageButton.setAttribute(
        "aria-label",
        tr(`Подробнее: ${product.title.ru}`, `View ${product.title.en}`),
      );
      const image = element("img");
      image.src = `/images/${product.image}`;
      image.alt = product.title[state.language];
      image.width = 300;
      image.height = 260;
      imageButton.append(image);
      const info = element("div", "product-info");
      info.append(
        button(product.title[state.language], "product-title", () =>
          showProduct(product),
        ),
        element(
          "p",
          "product-description",
          product.description[state.language],
        ),
      );
      const bottom = element("div", "product-bottom");
      bottom.append(
        element("span", "price", money(product.price)),
        quantityControl(product),
      );
      info.append(bottom);
      card.append(imageButton, info);
      return card;
    }),
  );
  if (!products.length)
    $("#products").append(
      element(
        "p",
        "empty-state",
        tr(
          "Ничего не нашли. Попробуйте другой запрос или категорию.",
          "Nothing found. Try another search or category.",
        ),
      ),
    );
}
function renderCartBadge() {
  $("#cart-button").replaceChildren(
    document.createTextNode(tr("Корзина ", "Cart ")),
    element("span", "", String(state.cart.count)),
  );
  $("#floating-cart").hidden = !state.cart.count;
  $("#floating-label").textContent = tr(
    `Корзина · ${state.cart.count}`,
    `Cart · ${state.cart.count}`,
  );
  $("#floating-total").textContent = `${money(state.cart.subtotal)} →`;
}
async function updateQuantity(id, quantity) {
  if (state.busy || !state.ready) return;
  state.busy = true;
  clearError();
  try {
    state.cart = await api(`/cart/items/${id}`, {
      method: "PUT",
      body: JSON.stringify({ quantity }),
    });
    renderProducts();
    renderCartBadge();
    if (state.dialog === "cart") showCart();
    if (state.dialog === "product") showProduct(state.detailProduct);
    if (tg?.initData && tg.isVersionAtLeast("6.1"))
      tg.HapticFeedback?.selectionChanged();
  } catch (error) {
    report(error);
    toast(error.message);
  } finally {
    state.busy = false;
  }
}
function showProduct(product) {
  if (!product) return;
  state.dialog = "product";
  state.detailProduct = product;
  const body = openDialog(product.title[state.language]);
  const image = element("img", "detail-image");
  image.src = `/images/${product.image}`;
  image.alt = product.title[state.language];
  body.append(
    image,
    element("p", "detail-copy", product.description[state.language]),
    element("p", "price", money(product.price)),
    quantityControl(product),
    element(
      "p",
      "small-note",
      tr(
        "Демонстрационный товар. Купить по-настоящему нельзя.",
        "A fictional demo product. Not available for real purchase.",
      ),
    ),
  );
}
function showCart() {
  state.dialog = "cart";
  const body = openDialog(tr("Ваша корзина", "Your cart"));
  if (!state.cart.count) {
    body.append(
      element(
        "p",
        "empty-state",
        tr(
          "Здесь пока пусто. Найдём что-нибудь хорошее?",
          "Nothing here yet. Find something you like?",
        ),
      ),
      button(
        tr("К каталогу", "Browse catalogue"),
        "primary-button",
        closeDialog,
      ),
    );
    return;
  }
  for (const line of state.cart.lines) {
    const row = element("div", "cart-line"),
      image = element("img");
    image.src = `/images/${line.image}`;
    image.alt = line.title[state.language];
    const text = element("div");
    text.append(
      element("h3", "", line.title[state.language]),
      element("p", "", money(line.line_total)),
    );
    row.append(image, text, quantityControl(line));
    body.append(row);
  }
  const total = element("div", "totals");
  total.append(
    element("span", "", tr("Товары", "Subtotal")),
    element("span", "", money(state.cart.subtotal)),
  );
  body.append(
    total,
    button(
      tr("Оформить заказ →", "Checkout →"),
      "primary-button",
      showCheckout,
    ),
    element(
      "p",
      "small-note",
      tr(
        "Это демо. Вводить данные настоящей карты не нужно.",
        "This is a demo. No real card details are needed.",
      ),
    ),
  );
}
function showCheckout() {
  state.dialog = "checkout";
  state.checkoutKey ||= crypto.randomUUID().replaceAll("-", "");
  const body = openDialog(tr("Оформление заказа", "Checkout")),
    form = element("form", "checkout-form");
  const controls = {};
  function input(name, label, placeholder, maxLength) {
    const wrapper = element("label", "", label),
      control = element("input");
    control.name = name;
    control.required = true;
    control.maxLength = maxLength;
    control.placeholder = placeholder;
    control.autocomplete = "off";
    wrapper.append(control);
    form.append(wrapper);
    controls[name] = control;
    return wrapper;
  }
  input(
    "customer_name",
    tr("Ваше имя", "Your name"),
    tr("Например, Алекс", "For example, Alex"),
    80,
  );
  input(
    "contact",
    tr("Контакт для связи", "Contact"),
    tr("Телефон, email или @username", "Phone, email or @username"),
    120,
  );
  const fulfillmentLabel = element(
      "label",
      "",
      tr("Как получить", "Fulfillment"),
    ),
    select = element("select");
  for (const [value, text] of [
    ["pickup", tr("Самовывоз · бесплатно", "Pickup · free")],
    [
      "delivery",
      tr(
        "Доставка · 300 ₽, от 3 000 ₽ бесплатно",
        "Delivery · ₽300, free from ₽3,000",
      ),
    ],
  ]) {
    const option = element("option", "", text);
    option.value = value;
    select.append(option);
  }
  fulfillmentLabel.append(select);
  form.append(fulfillmentLabel);
  const addressLabel = input(
    "address",
    tr("Адрес доставки", "Delivery address"),
    tr("Город, улица, дом", "City, street, building"),
    300,
  );
  addressLabel.hidden = true;
  controls.address.required = false;
  const total = element("div", "totals");
  const totalAmount = element("strong", "", money(state.cart.subtotal));
  total.append(element("span", "", tr("Итого", "Total")), totalAmount);
  form.append(total);
  select.addEventListener("change", () => {
    const delivery = select.value === "delivery";
    addressLabel.hidden = !delivery;
    controls.address.required = delivery;
    totalAmount.textContent = money(
      state.cart.subtotal +
        (delivery && state.cart.subtotal < 300000 ? 30000 : 0),
    );
  });
  const errorNode = element("p", "form-error");
  errorNode.setAttribute("role", "alert");
  errorNode.hidden = true;
  const submit = element(
    "button",
    "primary-button",
    tr("Создать демо-заказ", "Place demo order"),
  );
  submit.type = "submit";
  form.append(
    element(
      "p",
      "small-note",
      tr(
        "Можно указать вымышленные данные. Отправки товаров и списания денег не будет.",
        "You can use fictional details. No goods will be shipped and no money charged.",
      ),
    ),
    errorNode,
    submit,
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.busy) return;
    state.busy = true;
    submit.disabled = true;
    errorNode.hidden = true;
    try {
      const order = await api("/orders", {
        method: "POST",
        body: JSON.stringify({
          request_key: state.checkoutKey,
          customer_name: controls.customer_name.value,
          contact: controls.contact.value,
          fulfillment: select.value,
          address: controls.address.value,
        }),
      });
      state.checkoutKey = null;
      state.cart = { lines: [], count: 0, subtotal: 0 };
      renderProducts();
      renderCartBadge();
      showOrder(order);
    } catch (error) {
      errorNode.textContent = error.message;
      errorNode.hidden = false;
    } finally {
      state.busy = false;
      submit.disabled = false;
    }
  });
  body.append(form);
  controls.customer_name.focus();
}
function showOrder(order) {
  state.dialog = "order";
  const body = openDialog(
    tr(`Заказ #${order.id.slice(0, 8)}`, `Order #${order.id.slice(0, 8)}`),
  );
  body.append(
    element(
      "p",
      "payment-label",
      tr(
        "Демонстрация оплаты. Выберите результат, чтобы увидеть поведение заказа. Деньги не списываются.",
        "Payment simulation. Choose an outcome to see how the order behaves. No money is charged.",
      ),
    ),
    element("p", "order-status", statusText(order.status)),
  );
  const lines = element("div", "order-lines");
  for (const line of order.lines)
    lines.append(
      element(
        "div",
        "",
        `${line.title[state.language]} × ${line.quantity} · ${money(line.line_total)}`,
      ),
    );
  body.append(
    lines,
    element(
      "p",
      "small-note",
      order.fulfillment === "delivery"
        ? tr(`Доставка: ${order.address}`, `Delivery: ${order.address}`)
        : tr("Самовывоз · демо", "Pickup · demo"),
    ),
  );
  if (order.shipping)
    body.append(
      element(
        "p",
        "small-note",
        tr("Доставка: ", "Shipping: ") + money(order.shipping),
      ),
    );
  body.append(element("p", "order-total", money(order.total)));
  if (["awaiting_payment", "payment_failed"].includes(order.status)) {
    const controls = element("div", "payment-controls");
    for (const [outcome, label, className] of [
      [
        "success",
        tr("Успешная оплата", "Successful payment"),
        "primary-button",
      ],
      ["failure", tr("Отказ оплаты", "Payment failure"), "secondary-button"],
      ["cancel", tr("Отменить заказ", "Cancel order"), "secondary-button"],
    ]) {
      controls.append(
        button(label, className, async () => {
          if (state.busy) return;
          state.busy = true;
          try {
            const updated = await api(`/orders/${order.id}/payment`, {
              method: "POST",
              body: JSON.stringify({ outcome }),
            });
            showOrder(updated);
            if (!$("#orders-section").hidden) await loadOrders();
          } catch (error) {
            toast(error.message);
          } finally {
            state.busy = false;
          }
        }),
      );
    }
    body.append(controls);
  } else
    body.append(
      button(
        tr("Продолжить покупки", "Continue shopping"),
        "primary-button",
        () => {
          closeDialog();
          showCatalogue();
        },
      ),
    );
}
function showCatalogue() {
  $("#catalog").hidden = false;
  $("#orders-section").hidden = true;
  $(".hero").hidden = false;
}
async function loadOrders() {
  const data = await api("/orders");
  $("#orders-list").replaceChildren(
    ...data.orders.map((order) => {
      const row = element("article", "order-card"),
        info = element("div");
      info.append(
        element("h3", "", `#${order.id.slice(0, 8)} · ${money(order.total)}`),
        element("p", "", statusText(order.status)),
      );
      row.append(
        info,
        button(tr("Открыть", "View"), "", () => showOrder(order)),
      );
      return row;
    }),
  );
  if (!data.orders.length)
    $("#orders-list").append(
      element(
        "p",
        "empty-state",
        tr(
          "Заказов пока нет. Первый начинается с корзины.",
          "No orders yet. Your first one starts in the cart.",
        ),
      ),
    );
}
async function showOrders() {
  if (!state.ready) return;
  clearError();
  try {
    await loadOrders();
    $("#catalog").hidden = true;
    $(".hero").hidden = true;
    $("#orders-section").hidden = false;
    $("#orders-section").scrollIntoView();
  } catch (error) {
    report(error);
  }
}
async function init() {
  clearError();
  try {
    tg?.ready();
    tg?.expand();
    const [session, catalogue] = await Promise.all([
      api("/session", { method: "POST" }),
      api("/catalog"),
    ]);
    if (!localStorage.getItem("shop-language"))
      state.language = session.language;
    state.products = catalogue.products;
    state.cart = await api("/cart");
    state.ready = true;
    renderCopy();
  } catch (error) {
    report(error);
    $("#error-banner").append(button(tr("Повторить", "Retry"), "", init));
  }
}
$("#search").addEventListener("input", renderProducts);
$("#hero-product").addEventListener("click", () =>
  showProduct(state.products.find((p) => p.id === "notebook")),
);
$("#cart-button").addEventListener("click", () => {
  if (state.ready) showCart();
});
$("#floating-cart").addEventListener("click", showCart);
$("#close-dialog").addEventListener("click", closeDialog);
$("#shop-dialog").addEventListener("close", () => {
  state.dialog = null;
});
$("#orders-button").addEventListener("click", showOrders);
$("#back-catalog").addEventListener("click", showCatalogue);
$("#language-button").addEventListener("click", async () => {
  state.language = state.language === "ru" ? "en" : "ru";
  localStorage.setItem("shop-language", state.language);
  closeDialog();
  renderCopy();
  if (!$("#orders-section").hidden) {
    try {
      await loadOrders();
    } catch (error) {
      report(error);
    }
  }
});
renderCopy();
init();
