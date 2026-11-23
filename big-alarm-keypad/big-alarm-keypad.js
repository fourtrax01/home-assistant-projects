// big-alarm-keypad: large square keypad for an alarm_control_panel entity.
// Config:
//   type: custom:big-alarm-keypad
//   entity: alarm_control_panel.alarm
//   states: [arm_home, arm_away]   # arm buttons shown while disarmed
//   code_length: 4                 # optional: shows empty slots for the remaining digits
// The typed code lives only in this browser tab; it is sent once with the service call.

const LABELS = {
  arm_home: "Arm Home",
  arm_away: "Arm Away",
  arm_night: "Arm Night",
  arm_vacation: "Arm Vacation",
  arm_custom_bypass: "Arm Bypass",
};
const ICONS = {
  disarmed: "mdi:shield-check",
  armed_home: "mdi:shield-home",
  armed_away: "mdi:shield-lock",
  armed_night: "mdi:shield-moon",
  armed_vacation: "mdi:shield-airplane",
  armed_custom_bypass: "mdi:security",
  arming: "mdi:shield-sync",
  pending: "mdi:shield-alert",
  triggered: "mdi:bell-ring",
};
const MAX_DIGITS = 12;

class BigAlarmKeypad extends HTMLElement {
  static getStubConfig() {
    return { entity: "alarm_control_panel.alarm", states: ["arm_home", "arm_away"] };
  }

  setConfig(config) {
    if (!config || !config.entity) throw new Error("entity is required");
    this._config = { states: ["arm_home", "arm_away"], ...config };
    this._code = "";
    this._msg = "";
    this._busy = false;
    if (this._root) this._render();
  }

  getCardSize() {
    return 10;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._root) this._build();
    const st = hass.states[this._config.entity];
    const state = st ? st.state : "unavailable";
    if (state !== this._state) {
      this._state = state;
      this._code = "";
      this._msg = "";
      this._render();
    }
  }

  _build() {
    this._root = this.attachShadow({ mode: "open" });
    this._root.innerHTML = `
      <style>
        ha-card { padding: 16px; }
        .head { display: flex; align-items: center; justify-content: center; gap: 10px;
                font-size: 22px; font-weight: 600; color: var(--state-color); }
        .head ha-icon { --mdc-icon-size: 30px; }
        .dots { display: flex; justify-content: center; align-items: center; gap: 18px;
                min-height: 44px; margin: 18px 0 8px; flex-wrap: wrap; }
        .dot { width: 22px; height: 22px; border-radius: 50%; box-sizing: border-box;
               border: 3px solid var(--primary-text-color); }
        .dot.on { background: var(--primary-text-color); }
        .hint { font-size: 18px; color: var(--secondary-text-color); }
        .msg { text-align: center; min-height: 24px; font-size: 18px; font-weight: 600;
               color: var(--error-color, #db4437); }
        .shake { animation: shake .35s; }
        @keyframes shake { 0%,100% { transform: translateX(0); } 20%,60% { transform: translateX(-10px); }
                           40%,80% { transform: translateX(10px); } }
        .pad { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;
               max-width: 380px; margin: 8px auto 0; }
        button { font-family: inherit; cursor: pointer; border: none; color: var(--primary-text-color);
                 touch-action: manipulation; -webkit-tap-highlight-color: transparent; user-select: none; }
        .key { aspect-ratio: 1 / 1; border-radius: 18px; font-size: clamp(28px, 8vw, 40px); font-weight: 500;
               background: var(--secondary-background-color, rgba(127,127,127,.18));
               transition: transform .06s, filter .06s; }
        .key.small { font-size: 18px; }
        .key:active, .act:active { transform: scale(.93); filter: brightness(1.4); }
        .acts { display: grid; gap: 12px; max-width: 380px; margin: 16px auto 0;
                grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); }
        .act { height: 64px; border-radius: 16px; font-size: 20px; font-weight: 600; color: #fff;
               background: var(--act-color, var(--primary-color)); }
        .act[disabled] { opacity: .5; }
      </style>
      <ha-card>
        <div class="head"><ha-icon></ha-icon><span class="state"></span></div>
        <div class="dots"></div>
        <div class="msg"></div>
        <div class="pad"></div>
        <div class="acts"></div>
      </ha-card>`;
    const pad = this._root.querySelector(".pad");
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "clear", "0", "back"].forEach((k) => {
      const b = document.createElement("button");
      b.className = "key" + (k === "clear" ? " small" : "");
      b.textContent = k === "clear" ? "Clear" : k === "back" ? "⌫" : k;
      b.setAttribute("aria-label", k === "back" ? "Backspace" : k);
      b.addEventListener("click", () => this._press(k));
      pad.appendChild(b);
    });
  }

  _haptic() {
    window.dispatchEvent(new CustomEvent("haptic", { detail: "light" }));
  }

  _press(k) {
    this._haptic();
    this._msg = "";
    if (k === "clear") this._code = "";
    else if (k === "back") this._code = this._code.slice(0, -1);
    else if (this._code.length < MAX_DIGITS) this._code += k;
    this._renderDots();
    this._root.querySelector(".msg").textContent = "";
  }

  _stateColor(state) {
    if (state === "disarmed") return "var(--success-color, #43a047)";
    if (state === "triggered" || state.startsWith("armed")) return "var(--error-color, #db4437)";
    if (state === "arming" || state === "pending") return "var(--warning-color, #ffa600)";
    return "var(--secondary-text-color)";
  }

  _renderDots() {
    const dots = this._root.querySelector(".dots");
    const len = Number(this._config.code_length) || 0;
    const n = Math.max(len, this._code.length);
    if (n === 0) {
      dots.innerHTML = `<span class="hint">Enter code</span>`;
      return;
    }
    dots.innerHTML = Array.from({ length: n }, (_, i) =>
      `<span class="dot${i < this._code.length ? " on" : ""}"></span>`).join("");
  }

  _render() {
    if (!this._root || !this._hass) return;
    const st = this._hass.states[this._config.entity];
    const state = st ? st.state : "unavailable";
    const card = this._root.querySelector("ha-card");
    card.style.setProperty("--state-color", this._stateColor(state));
    this._root.querySelector(".head ha-icon").setAttribute("icon", ICONS[state] || "mdi:shield");
    let label = state;
    try {
      if (st && this._hass.formatEntityState) label = this._hass.formatEntityState(st);
    } catch (e) { /* fall back to raw state */ }
    this._root.querySelector(".state").textContent = label;

    const needsPad = st && st.attributes.code_format === "number";
    this._root.querySelector(".pad").style.display = needsPad ? "" : "none";
    this._root.querySelector(".dots").style.display = needsPad ? "" : "none";
    this._root.querySelector(".msg").textContent = this._msg;
    this._renderDots();

    const acts = this._root.querySelector(".acts");
    acts.innerHTML = "";
    const add = (text, service, color) => {
      const b = document.createElement("button");
      b.className = "act";
      b.textContent = text;
      b.style.setProperty("--act-color", color);
      b.disabled = this._busy || state === "unavailable";
      b.addEventListener("click", () => this._call(service));
      acts.appendChild(b);
    };
    if (state === "disarmed") {
      this._config.states.forEach((s) =>
        add(LABELS[s] || s, "alarm_" + s, "var(--error-color, #db4437)"));
    } else {
      add("Disarm", "alarm_disarm", "var(--success-color, #43a047)");
    }
  }

  async _call(service) {
    this._haptic();
    const data = { entity_id: this._config.entity };
    if (this._code) data.code = this._code;
    this._busy = true;
    this._render();
    try {
      await this._hass.callService("alarm_control_panel", service, data);
      this._code = "";
      this._msg = "";
    } catch (e) {
      this._code = "";
      this._msg = /code/i.test((e && e.message) || "") ? "Wrong code" : "Failed: " + ((e && e.message) || "error");
      const dots = this._root.querySelector(".dots");
      dots.classList.remove("shake");
      void dots.offsetWidth;
      dots.classList.add("shake");
    }
    this._busy = false;
    this._render();
  }
}

customElements.define("big-alarm-keypad", BigAlarmKeypad);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "big-alarm-keypad",
  name: "Big Alarm Keypad",
  description: "Large square keypad with big digit dots for an alarm panel",
});
