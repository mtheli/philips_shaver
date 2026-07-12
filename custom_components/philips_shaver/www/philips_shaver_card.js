
function $parcel$interopDefault(a) {
  return a && a.__esModule ? a.default : a;
}
/**
 * Philips Shaver Card for Home Assistant
 * https://github.com/mtheli/philips_shaver_card
 */ /**
 * @license
 * Copyright 2019 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */ const $06bdd16cbb4a41b3$var$t = globalThis, $06bdd16cbb4a41b3$export$b4d10f6001c083c2 = $06bdd16cbb4a41b3$var$t.ShadowRoot && (void 0 === $06bdd16cbb4a41b3$var$t.ShadyCSS || $06bdd16cbb4a41b3$var$t.ShadyCSS.nativeShadow) && "adoptedStyleSheets" in Document.prototype && "replace" in CSSStyleSheet.prototype, $06bdd16cbb4a41b3$var$s = Symbol(), $06bdd16cbb4a41b3$var$o = new WeakMap;
class $06bdd16cbb4a41b3$export$505d1e8739bad805 {
    constructor(t, e, o){
        if (this._$cssResult$ = !0, o !== $06bdd16cbb4a41b3$var$s) throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");
        this.cssText = t, this.t = e;
    }
    get styleSheet() {
        let t = this.o;
        const s = this.t;
        if ($06bdd16cbb4a41b3$export$b4d10f6001c083c2 && void 0 === t) {
            const e = void 0 !== s && 1 === s.length;
            e && (t = $06bdd16cbb4a41b3$var$o.get(s)), void 0 === t && ((this.o = t = new CSSStyleSheet).replaceSync(this.cssText), e && $06bdd16cbb4a41b3$var$o.set(s, t));
        }
        return t;
    }
    toString() {
        return this.cssText;
    }
}
const $06bdd16cbb4a41b3$export$8d80f9cac07cdb3 = (t)=>new $06bdd16cbb4a41b3$export$505d1e8739bad805("string" == typeof t ? t : t + "", void 0, $06bdd16cbb4a41b3$var$s), $06bdd16cbb4a41b3$export$dbf350e5966cf602 = (t, ...e)=>{
    const o = 1 === t.length ? t[0] : e.reduce((e, s, o)=>e + ((t)=>{
            if (!0 === t._$cssResult$) return t.cssText;
            if ("number" == typeof t) return t;
            throw Error("Value passed to 'css' function must be a 'css' function result: " + t + ". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.");
        })(s) + t[o + 1], t[0]);
    return new $06bdd16cbb4a41b3$export$505d1e8739bad805(o, t, $06bdd16cbb4a41b3$var$s);
}, $06bdd16cbb4a41b3$export$2ca4a66ec4cecb90 = (s, o)=>{
    if ($06bdd16cbb4a41b3$export$b4d10f6001c083c2) s.adoptedStyleSheets = o.map((t)=>t instanceof CSSStyleSheet ? t : t.styleSheet);
    else for (const e of o){
        const o = document.createElement("style"), n = $06bdd16cbb4a41b3$var$t.litNonce;
        void 0 !== n && o.setAttribute("nonce", n), o.textContent = e.cssText, s.appendChild(o);
    }
}, $06bdd16cbb4a41b3$export$ee69dfd951e24778 = $06bdd16cbb4a41b3$export$b4d10f6001c083c2 ? (t)=>t : (t)=>t instanceof CSSStyleSheet ? ((t)=>{
        let e = "";
        for (const s of t.cssRules)e += s.cssText;
        return $06bdd16cbb4a41b3$export$8d80f9cac07cdb3(e);
    })(t) : t;


/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */ const { is: $375b48187e686ca2$var$i, defineProperty: $375b48187e686ca2$var$e, getOwnPropertyDescriptor: $375b48187e686ca2$var$h, getOwnPropertyNames: $375b48187e686ca2$var$r, getOwnPropertySymbols: $375b48187e686ca2$var$o, getPrototypeOf: $375b48187e686ca2$var$n } = Object, $375b48187e686ca2$var$a = globalThis, $375b48187e686ca2$var$c = $375b48187e686ca2$var$a.trustedTypes, $375b48187e686ca2$var$l = $375b48187e686ca2$var$c ? $375b48187e686ca2$var$c.emptyScript : "", $375b48187e686ca2$var$p = $375b48187e686ca2$var$a.reactiveElementPolyfillSupport, $375b48187e686ca2$var$d = (t, s)=>t, $375b48187e686ca2$export$7312b35fbf521afb = {
    toAttribute (t, s) {
        switch(s){
            case Boolean:
                t = t ? $375b48187e686ca2$var$l : null;
                break;
            case Object:
            case Array:
                t = null == t ? t : JSON.stringify(t);
        }
        return t;
    },
    fromAttribute (t, s) {
        let i = t;
        switch(s){
            case Boolean:
                i = null !== t;
                break;
            case Number:
                i = null === t ? null : Number(t);
                break;
            case Object:
            case Array:
                try {
                    i = JSON.parse(t);
                } catch (t) {
                    i = null;
                }
        }
        return i;
    }
}, $375b48187e686ca2$export$53a6892c50694894 = (t, s)=>!$375b48187e686ca2$var$i(t, s), $375b48187e686ca2$var$b = {
    attribute: !0,
    type: String,
    converter: $375b48187e686ca2$export$7312b35fbf521afb,
    reflect: !1,
    useDefault: !1,
    hasChanged: $375b48187e686ca2$export$53a6892c50694894
};
Symbol.metadata ??= Symbol("metadata"), $375b48187e686ca2$var$a.litPropertyMetadata ??= new WeakMap;
class $375b48187e686ca2$export$c7c07a37856565d extends HTMLElement {
    static addInitializer(t) {
        this._$Ei(), (this.l ??= []).push(t);
    }
    static get observedAttributes() {
        return this.finalize(), this._$Eh && [
            ...this._$Eh.keys()
        ];
    }
    static createProperty(t, s = $375b48187e686ca2$var$b) {
        if (s.state && (s.attribute = !1), this._$Ei(), this.prototype.hasOwnProperty(t) && ((s = Object.create(s)).wrapped = !0), this.elementProperties.set(t, s), !s.noAccessor) {
            const i = Symbol(), h = this.getPropertyDescriptor(t, i, s);
            void 0 !== h && $375b48187e686ca2$var$e(this.prototype, t, h);
        }
    }
    static getPropertyDescriptor(t, s, i) {
        const { get: e, set: r } = $375b48187e686ca2$var$h(this.prototype, t) ?? {
            get () {
                return this[s];
            },
            set (t) {
                this[s] = t;
            }
        };
        return {
            get: e,
            set (s) {
                const h = e?.call(this);
                r?.call(this, s), this.requestUpdate(t, h, i);
            },
            configurable: !0,
            enumerable: !0
        };
    }
    static getPropertyOptions(t) {
        return this.elementProperties.get(t) ?? $375b48187e686ca2$var$b;
    }
    static _$Ei() {
        if (this.hasOwnProperty($375b48187e686ca2$var$d("elementProperties"))) return;
        const t = $375b48187e686ca2$var$n(this);
        t.finalize(), void 0 !== t.l && (this.l = [
            ...t.l
        ]), this.elementProperties = new Map(t.elementProperties);
    }
    static finalize() {
        if (this.hasOwnProperty($375b48187e686ca2$var$d("finalized"))) return;
        if (this.finalized = !0, this._$Ei(), this.hasOwnProperty($375b48187e686ca2$var$d("properties"))) {
            const t = this.properties, s = [
                ...$375b48187e686ca2$var$r(t),
                ...$375b48187e686ca2$var$o(t)
            ];
            for (const i of s)this.createProperty(i, t[i]);
        }
        const t = this[Symbol.metadata];
        if (null !== t) {
            const s = litPropertyMetadata.get(t);
            if (void 0 !== s) for (const [t, i] of s)this.elementProperties.set(t, i);
        }
        this._$Eh = new Map;
        for (const [t, s] of this.elementProperties){
            const i = this._$Eu(t, s);
            void 0 !== i && this._$Eh.set(i, t);
        }
        this.elementStyles = this.finalizeStyles(this.styles);
    }
    static finalizeStyles(s) {
        const i = [];
        if (Array.isArray(s)) {
            const e = new Set(s.flat(1 / 0).reverse());
            for (const s of e)i.unshift((0, $06bdd16cbb4a41b3$export$ee69dfd951e24778)(s));
        } else void 0 !== s && i.push((0, $06bdd16cbb4a41b3$export$ee69dfd951e24778)(s));
        return i;
    }
    static _$Eu(t, s) {
        const i = s.attribute;
        return !1 === i ? void 0 : "string" == typeof i ? i : "string" == typeof t ? t.toLowerCase() : void 0;
    }
    constructor(){
        super(), this._$Ep = void 0, this.isUpdatePending = !1, this.hasUpdated = !1, this._$Em = null, this._$Ev();
    }
    _$Ev() {
        this._$ES = new Promise((t)=>this.enableUpdating = t), this._$AL = new Map, this._$E_(), this.requestUpdate(), this.constructor.l?.forEach((t)=>t(this));
    }
    addController(t) {
        (this._$EO ??= new Set).add(t), void 0 !== this.renderRoot && this.isConnected && t.hostConnected?.();
    }
    removeController(t) {
        this._$EO?.delete(t);
    }
    _$E_() {
        const t = new Map, s = this.constructor.elementProperties;
        for (const i of s.keys())this.hasOwnProperty(i) && (t.set(i, this[i]), delete this[i]);
        t.size > 0 && (this._$Ep = t);
    }
    createRenderRoot() {
        const t = this.shadowRoot ?? this.attachShadow(this.constructor.shadowRootOptions);
        return (0, $06bdd16cbb4a41b3$export$2ca4a66ec4cecb90)(t, this.constructor.elementStyles), t;
    }
    connectedCallback() {
        this.renderRoot ??= this.createRenderRoot(), this.enableUpdating(!0), this._$EO?.forEach((t)=>t.hostConnected?.());
    }
    enableUpdating(t) {}
    disconnectedCallback() {
        this._$EO?.forEach((t)=>t.hostDisconnected?.());
    }
    attributeChangedCallback(t, s, i) {
        this._$AK(t, i);
    }
    _$ET(t, s) {
        const i = this.constructor.elementProperties.get(t), e = this.constructor._$Eu(t, i);
        if (void 0 !== e && !0 === i.reflect) {
            const h = (void 0 !== i.converter?.toAttribute ? i.converter : $375b48187e686ca2$export$7312b35fbf521afb).toAttribute(s, i.type);
            this._$Em = t, null == h ? this.removeAttribute(e) : this.setAttribute(e, h), this._$Em = null;
        }
    }
    _$AK(t, s) {
        const i = this.constructor, e = i._$Eh.get(t);
        if (void 0 !== e && this._$Em !== e) {
            const t = i.getPropertyOptions(e), h = "function" == typeof t.converter ? {
                fromAttribute: t.converter
            } : void 0 !== t.converter?.fromAttribute ? t.converter : $375b48187e686ca2$export$7312b35fbf521afb;
            this._$Em = e;
            const r = h.fromAttribute(s, t.type);
            this[e] = r ?? this._$Ej?.get(e) ?? r, this._$Em = null;
        }
    }
    requestUpdate(t, s, i, e = !1, h) {
        if (void 0 !== t) {
            const r = this.constructor;
            if (!1 === e && (h = this[t]), i ??= r.getPropertyOptions(t), !((i.hasChanged ?? $375b48187e686ca2$export$53a6892c50694894)(h, s) || i.useDefault && i.reflect && h === this._$Ej?.get(t) && !this.hasAttribute(r._$Eu(t, i)))) return;
            this.C(t, s, i);
        }
        !1 === this.isUpdatePending && (this._$ES = this._$EP());
    }
    C(t, s, { useDefault: i, reflect: e, wrapped: h }, r) {
        i && !(this._$Ej ??= new Map).has(t) && (this._$Ej.set(t, r ?? s ?? this[t]), !0 !== h || void 0 !== r) || (this._$AL.has(t) || (this.hasUpdated || i || (s = void 0), this._$AL.set(t, s)), !0 === e && this._$Em !== t && (this._$Eq ??= new Set).add(t));
    }
    async _$EP() {
        this.isUpdatePending = !0;
        try {
            await this._$ES;
        } catch (t) {
            Promise.reject(t);
        }
        const t = this.scheduleUpdate();
        return null != t && await t, !this.isUpdatePending;
    }
    scheduleUpdate() {
        return this.performUpdate();
    }
    performUpdate() {
        if (!this.isUpdatePending) return;
        if (!this.hasUpdated) {
            if (this.renderRoot ??= this.createRenderRoot(), this._$Ep) {
                for (const [t, s] of this._$Ep)this[t] = s;
                this._$Ep = void 0;
            }
            const t = this.constructor.elementProperties;
            if (t.size > 0) for (const [s, i] of t){
                const { wrapped: t } = i, e = this[s];
                !0 !== t || this._$AL.has(s) || void 0 === e || this.C(s, void 0, i, e);
            }
        }
        let t = !1;
        const s = this._$AL;
        try {
            t = this.shouldUpdate(s), t ? (this.willUpdate(s), this._$EO?.forEach((t)=>t.hostUpdate?.()), this.update(s)) : this._$EM();
        } catch (s) {
            throw t = !1, this._$EM(), s;
        }
        t && this._$AE(s);
    }
    willUpdate(t) {}
    _$AE(t) {
        this._$EO?.forEach((t)=>t.hostUpdated?.()), this.hasUpdated || (this.hasUpdated = !0, this.firstUpdated(t)), this.updated(t);
    }
    _$EM() {
        this._$AL = new Map, this.isUpdatePending = !1;
    }
    get updateComplete() {
        return this.getUpdateComplete();
    }
    getUpdateComplete() {
        return this._$ES;
    }
    shouldUpdate(t) {
        return !0;
    }
    update(t) {
        this._$Eq &&= this._$Eq.forEach((t)=>this._$ET(t, this[t])), this._$EM();
    }
    updated(t) {}
    firstUpdated(t) {}
}
$375b48187e686ca2$export$c7c07a37856565d.elementStyles = [], $375b48187e686ca2$export$c7c07a37856565d.shadowRootOptions = {
    mode: "open"
}, $375b48187e686ca2$export$c7c07a37856565d[$375b48187e686ca2$var$d("elementProperties")] = new Map, $375b48187e686ca2$export$c7c07a37856565d[$375b48187e686ca2$var$d("finalized")] = new Map, $375b48187e686ca2$var$p?.({
    ReactiveElement: $375b48187e686ca2$export$c7c07a37856565d
}), ($375b48187e686ca2$var$a.reactiveElementVersions ??= []).push("2.1.2");


/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */ const $d33ef1320595a3ac$var$t = globalThis, $d33ef1320595a3ac$var$i = (t)=>t, $d33ef1320595a3ac$var$s = $d33ef1320595a3ac$var$t.trustedTypes, $d33ef1320595a3ac$var$e = $d33ef1320595a3ac$var$s ? $d33ef1320595a3ac$var$s.createPolicy("lit-html", {
    createHTML: (t)=>t
}) : void 0, $d33ef1320595a3ac$var$h = "$lit$", $d33ef1320595a3ac$var$o = `lit$${Math.random().toFixed(9).slice(2)}$`, $d33ef1320595a3ac$var$n = "?" + $d33ef1320595a3ac$var$o, $d33ef1320595a3ac$var$r = `<${$d33ef1320595a3ac$var$n}>`, $d33ef1320595a3ac$var$l = document, $d33ef1320595a3ac$var$c = ()=>$d33ef1320595a3ac$var$l.createComment(""), $d33ef1320595a3ac$var$a = (t)=>null === t || "object" != typeof t && "function" != typeof t, $d33ef1320595a3ac$var$u = Array.isArray, $d33ef1320595a3ac$var$d = (t)=>$d33ef1320595a3ac$var$u(t) || "function" == typeof t?.[Symbol.iterator], $d33ef1320595a3ac$var$f = "[ \t\n\f\r]", $d33ef1320595a3ac$var$v = /<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g, $d33ef1320595a3ac$var$_ = /-->/g, $d33ef1320595a3ac$var$m = />/g, $d33ef1320595a3ac$var$p = RegExp(`>|${$d33ef1320595a3ac$var$f}(?:([^\\s"'>=/]+)(${$d33ef1320595a3ac$var$f}*=${$d33ef1320595a3ac$var$f}*(?:[^ \t\n\f\r"'\`<>=]|("|')|))|$)`, "g"), $d33ef1320595a3ac$var$g = /'/g, $d33ef1320595a3ac$var$$ = /"/g, $d33ef1320595a3ac$var$y = /^(?:script|style|textarea|title)$/i, $d33ef1320595a3ac$var$x = (t)=>(i, ...s)=>({
            _$litType$: t,
            strings: i,
            values: s
        }), $d33ef1320595a3ac$export$c0bb0b647f701bb5 = $d33ef1320595a3ac$var$x(1), $d33ef1320595a3ac$export$7ed1367e7fa1ad68 = $d33ef1320595a3ac$var$x(2), $d33ef1320595a3ac$export$47d5b44d225be5b4 = $d33ef1320595a3ac$var$x(3), $d33ef1320595a3ac$export$9c068ae9cc5db4e8 = Symbol.for("lit-noChange"), $d33ef1320595a3ac$export$45b790e32b2810ee = Symbol.for("lit-nothing"), $d33ef1320595a3ac$var$C = new WeakMap, $d33ef1320595a3ac$var$P = $d33ef1320595a3ac$var$l.createTreeWalker($d33ef1320595a3ac$var$l, 129);
function $d33ef1320595a3ac$var$V(t, i) {
    if (!$d33ef1320595a3ac$var$u(t) || !t.hasOwnProperty("raw")) throw Error("invalid template strings array");
    return void 0 !== $d33ef1320595a3ac$var$e ? $d33ef1320595a3ac$var$e.createHTML(i) : i;
}
const $d33ef1320595a3ac$var$N = (t, i)=>{
    const s = t.length - 1, e = [];
    let n, l = 2 === i ? "<svg>" : 3 === i ? "<math>" : "", c = $d33ef1320595a3ac$var$v;
    for(let i = 0; i < s; i++){
        const s = t[i];
        let a, u, d = -1, f = 0;
        for(; f < s.length && (c.lastIndex = f, u = c.exec(s), null !== u);)f = c.lastIndex, c === $d33ef1320595a3ac$var$v ? "!--" === u[1] ? c = $d33ef1320595a3ac$var$_ : void 0 !== u[1] ? c = $d33ef1320595a3ac$var$m : void 0 !== u[2] ? ($d33ef1320595a3ac$var$y.test(u[2]) && (n = RegExp("</" + u[2], "g")), c = $d33ef1320595a3ac$var$p) : void 0 !== u[3] && (c = $d33ef1320595a3ac$var$p) : c === $d33ef1320595a3ac$var$p ? ">" === u[0] ? (c = n ?? $d33ef1320595a3ac$var$v, d = -1) : void 0 === u[1] ? d = -2 : (d = c.lastIndex - u[2].length, a = u[1], c = void 0 === u[3] ? $d33ef1320595a3ac$var$p : '"' === u[3] ? $d33ef1320595a3ac$var$$ : $d33ef1320595a3ac$var$g) : c === $d33ef1320595a3ac$var$$ || c === $d33ef1320595a3ac$var$g ? c = $d33ef1320595a3ac$var$p : c === $d33ef1320595a3ac$var$_ || c === $d33ef1320595a3ac$var$m ? c = $d33ef1320595a3ac$var$v : (c = $d33ef1320595a3ac$var$p, n = void 0);
        const x = c === $d33ef1320595a3ac$var$p && t[i + 1].startsWith("/>") ? " " : "";
        l += c === $d33ef1320595a3ac$var$v ? s + $d33ef1320595a3ac$var$r : d >= 0 ? (e.push(a), s.slice(0, d) + $d33ef1320595a3ac$var$h + s.slice(d) + $d33ef1320595a3ac$var$o + x) : s + $d33ef1320595a3ac$var$o + (-2 === d ? i : x);
    }
    return [
        $d33ef1320595a3ac$var$V(t, l + (t[s] || "<?>") + (2 === i ? "</svg>" : 3 === i ? "</math>" : "")),
        e
    ];
};
class $d33ef1320595a3ac$var$S {
    constructor({ strings: t, _$litType$: i }, e){
        let r;
        this.parts = [];
        let l = 0, a = 0;
        const u = t.length - 1, d = this.parts, [f, v] = $d33ef1320595a3ac$var$N(t, i);
        if (this.el = $d33ef1320595a3ac$var$S.createElement(f, e), $d33ef1320595a3ac$var$P.currentNode = this.el.content, 2 === i || 3 === i) {
            const t = this.el.content.firstChild;
            t.replaceWith(...t.childNodes);
        }
        for(; null !== (r = $d33ef1320595a3ac$var$P.nextNode()) && d.length < u;){
            if (1 === r.nodeType) {
                if (r.hasAttributes()) for (const t of r.getAttributeNames())if (t.endsWith($d33ef1320595a3ac$var$h)) {
                    const i = v[a++], s = r.getAttribute(t).split($d33ef1320595a3ac$var$o), e = /([.?@])?(.*)/.exec(i);
                    d.push({
                        type: 1,
                        index: l,
                        name: e[2],
                        strings: s,
                        ctor: "." === e[1] ? $d33ef1320595a3ac$var$I : "?" === e[1] ? $d33ef1320595a3ac$var$L : "@" === e[1] ? $d33ef1320595a3ac$var$z : $d33ef1320595a3ac$var$H
                    }), r.removeAttribute(t);
                } else t.startsWith($d33ef1320595a3ac$var$o) && (d.push({
                    type: 6,
                    index: l
                }), r.removeAttribute(t));
                if ($d33ef1320595a3ac$var$y.test(r.tagName)) {
                    const t = r.textContent.split($d33ef1320595a3ac$var$o), i = t.length - 1;
                    if (i > 0) {
                        r.textContent = $d33ef1320595a3ac$var$s ? $d33ef1320595a3ac$var$s.emptyScript : "";
                        for(let s = 0; s < i; s++)r.append(t[s], $d33ef1320595a3ac$var$c()), $d33ef1320595a3ac$var$P.nextNode(), d.push({
                            type: 2,
                            index: ++l
                        });
                        r.append(t[i], $d33ef1320595a3ac$var$c());
                    }
                }
            } else if (8 === r.nodeType) {
                if (r.data === $d33ef1320595a3ac$var$n) d.push({
                    type: 2,
                    index: l
                });
                else {
                    let t = -1;
                    for(; -1 !== (t = r.data.indexOf($d33ef1320595a3ac$var$o, t + 1));)d.push({
                        type: 7,
                        index: l
                    }), t += $d33ef1320595a3ac$var$o.length - 1;
                }
            }
            l++;
        }
    }
    static createElement(t, i) {
        const s = $d33ef1320595a3ac$var$l.createElement("template");
        return s.innerHTML = t, s;
    }
}
function $d33ef1320595a3ac$var$M(t, i, s = t, e) {
    if (i === $d33ef1320595a3ac$export$9c068ae9cc5db4e8) return i;
    let h = void 0 !== e ? s._$Co?.[e] : s._$Cl;
    const o = $d33ef1320595a3ac$var$a(i) ? void 0 : i._$litDirective$;
    return h?.constructor !== o && (h?._$AO?.(!1), void 0 === o ? h = void 0 : (h = new o(t), h._$AT(t, s, e)), void 0 !== e ? (s._$Co ??= [])[e] = h : s._$Cl = h), void 0 !== h && (i = $d33ef1320595a3ac$var$M(t, h._$AS(t, i.values), h, e)), i;
}
class $d33ef1320595a3ac$var$R {
    constructor(t, i){
        this._$AV = [], this._$AN = void 0, this._$AD = t, this._$AM = i;
    }
    get parentNode() {
        return this._$AM.parentNode;
    }
    get _$AU() {
        return this._$AM._$AU;
    }
    u(t) {
        const { el: { content: i }, parts: s } = this._$AD, e = (t?.creationScope ?? $d33ef1320595a3ac$var$l).importNode(i, !0);
        $d33ef1320595a3ac$var$P.currentNode = e;
        let h = $d33ef1320595a3ac$var$P.nextNode(), o = 0, n = 0, r = s[0];
        for(; void 0 !== r;){
            if (o === r.index) {
                let i;
                2 === r.type ? i = new $d33ef1320595a3ac$var$k(h, h.nextSibling, this, t) : 1 === r.type ? i = new r.ctor(h, r.name, r.strings, this, t) : 6 === r.type && (i = new $d33ef1320595a3ac$var$Z(h, this, t)), this._$AV.push(i), r = s[++n];
            }
            o !== r?.index && (h = $d33ef1320595a3ac$var$P.nextNode(), o++);
        }
        return $d33ef1320595a3ac$var$P.currentNode = $d33ef1320595a3ac$var$l, e;
    }
    p(t) {
        let i = 0;
        for (const s of this._$AV)void 0 !== s && (void 0 !== s.strings ? (s._$AI(t, s, i), i += s.strings.length - 2) : s._$AI(t[i])), i++;
    }
}
class $d33ef1320595a3ac$var$k {
    get _$AU() {
        return this._$AM?._$AU ?? this._$Cv;
    }
    constructor(t, i, s, e){
        this.type = 2, this._$AH = $d33ef1320595a3ac$export$45b790e32b2810ee, this._$AN = void 0, this._$AA = t, this._$AB = i, this._$AM = s, this.options = e, this._$Cv = e?.isConnected ?? !0;
    }
    get parentNode() {
        let t = this._$AA.parentNode;
        const i = this._$AM;
        return void 0 !== i && 11 === t?.nodeType && (t = i.parentNode), t;
    }
    get startNode() {
        return this._$AA;
    }
    get endNode() {
        return this._$AB;
    }
    _$AI(t, i = this) {
        t = $d33ef1320595a3ac$var$M(this, t, i), $d33ef1320595a3ac$var$a(t) ? t === $d33ef1320595a3ac$export$45b790e32b2810ee || null == t || "" === t ? (this._$AH !== $d33ef1320595a3ac$export$45b790e32b2810ee && this._$AR(), this._$AH = $d33ef1320595a3ac$export$45b790e32b2810ee) : t !== this._$AH && t !== $d33ef1320595a3ac$export$9c068ae9cc5db4e8 && this._(t) : void 0 !== t._$litType$ ? this.$(t) : void 0 !== t.nodeType ? this.T(t) : $d33ef1320595a3ac$var$d(t) ? this.k(t) : this._(t);
    }
    O(t) {
        return this._$AA.parentNode.insertBefore(t, this._$AB);
    }
    T(t) {
        this._$AH !== t && (this._$AR(), this._$AH = this.O(t));
    }
    _(t) {
        this._$AH !== $d33ef1320595a3ac$export$45b790e32b2810ee && $d33ef1320595a3ac$var$a(this._$AH) ? this._$AA.nextSibling.data = t : this.T($d33ef1320595a3ac$var$l.createTextNode(t)), this._$AH = t;
    }
    $(t) {
        const { values: i, _$litType$: s } = t, e = "number" == typeof s ? this._$AC(t) : (void 0 === s.el && (s.el = $d33ef1320595a3ac$var$S.createElement($d33ef1320595a3ac$var$V(s.h, s.h[0]), this.options)), s);
        if (this._$AH?._$AD === e) this._$AH.p(i);
        else {
            const t = new $d33ef1320595a3ac$var$R(e, this), s = t.u(this.options);
            t.p(i), this.T(s), this._$AH = t;
        }
    }
    _$AC(t) {
        let i = $d33ef1320595a3ac$var$C.get(t.strings);
        return void 0 === i && $d33ef1320595a3ac$var$C.set(t.strings, i = new $d33ef1320595a3ac$var$S(t)), i;
    }
    k(t) {
        $d33ef1320595a3ac$var$u(this._$AH) || (this._$AH = [], this._$AR());
        const i = this._$AH;
        let s, e = 0;
        for (const h of t)e === i.length ? i.push(s = new $d33ef1320595a3ac$var$k(this.O($d33ef1320595a3ac$var$c()), this.O($d33ef1320595a3ac$var$c()), this, this.options)) : s = i[e], s._$AI(h), e++;
        e < i.length && (this._$AR(s && s._$AB.nextSibling, e), i.length = e);
    }
    _$AR(t = this._$AA.nextSibling, s) {
        for(this._$AP?.(!1, !0, s); t !== this._$AB;){
            const s = $d33ef1320595a3ac$var$i(t).nextSibling;
            $d33ef1320595a3ac$var$i(t).remove(), t = s;
        }
    }
    setConnected(t) {
        void 0 === this._$AM && (this._$Cv = t, this._$AP?.(t));
    }
}
class $d33ef1320595a3ac$var$H {
    get tagName() {
        return this.element.tagName;
    }
    get _$AU() {
        return this._$AM._$AU;
    }
    constructor(t, i, s, e, h){
        this.type = 1, this._$AH = $d33ef1320595a3ac$export$45b790e32b2810ee, this._$AN = void 0, this.element = t, this.name = i, this._$AM = e, this.options = h, s.length > 2 || "" !== s[0] || "" !== s[1] ? (this._$AH = Array(s.length - 1).fill(new String), this.strings = s) : this._$AH = $d33ef1320595a3ac$export$45b790e32b2810ee;
    }
    _$AI(t, i = this, s, e) {
        const h = this.strings;
        let o = !1;
        if (void 0 === h) t = $d33ef1320595a3ac$var$M(this, t, i, 0), o = !$d33ef1320595a3ac$var$a(t) || t !== this._$AH && t !== $d33ef1320595a3ac$export$9c068ae9cc5db4e8, o && (this._$AH = t);
        else {
            const e = t;
            let n, r;
            for(t = h[0], n = 0; n < h.length - 1; n++)r = $d33ef1320595a3ac$var$M(this, e[s + n], i, n), r === $d33ef1320595a3ac$export$9c068ae9cc5db4e8 && (r = this._$AH[n]), o ||= !$d33ef1320595a3ac$var$a(r) || r !== this._$AH[n], r === $d33ef1320595a3ac$export$45b790e32b2810ee ? t = $d33ef1320595a3ac$export$45b790e32b2810ee : t !== $d33ef1320595a3ac$export$45b790e32b2810ee && (t += (r ?? "") + h[n + 1]), this._$AH[n] = r;
        }
        o && !e && this.j(t);
    }
    j(t) {
        t === $d33ef1320595a3ac$export$45b790e32b2810ee ? this.element.removeAttribute(this.name) : this.element.setAttribute(this.name, t ?? "");
    }
}
class $d33ef1320595a3ac$var$I extends $d33ef1320595a3ac$var$H {
    constructor(){
        super(...arguments), this.type = 3;
    }
    j(t) {
        this.element[this.name] = t === $d33ef1320595a3ac$export$45b790e32b2810ee ? void 0 : t;
    }
}
class $d33ef1320595a3ac$var$L extends $d33ef1320595a3ac$var$H {
    constructor(){
        super(...arguments), this.type = 4;
    }
    j(t) {
        this.element.toggleAttribute(this.name, !!t && t !== $d33ef1320595a3ac$export$45b790e32b2810ee);
    }
}
class $d33ef1320595a3ac$var$z extends $d33ef1320595a3ac$var$H {
    constructor(t, i, s, e, h){
        super(t, i, s, e, h), this.type = 5;
    }
    _$AI(t, i = this) {
        if ((t = $d33ef1320595a3ac$var$M(this, t, i, 0) ?? $d33ef1320595a3ac$export$45b790e32b2810ee) === $d33ef1320595a3ac$export$9c068ae9cc5db4e8) return;
        const s = this._$AH, e = t === $d33ef1320595a3ac$export$45b790e32b2810ee && s !== $d33ef1320595a3ac$export$45b790e32b2810ee || t.capture !== s.capture || t.once !== s.once || t.passive !== s.passive, h = t !== $d33ef1320595a3ac$export$45b790e32b2810ee && (s === $d33ef1320595a3ac$export$45b790e32b2810ee || e);
        e && this.element.removeEventListener(this.name, this, s), h && this.element.addEventListener(this.name, this, t), this._$AH = t;
    }
    handleEvent(t) {
        "function" == typeof this._$AH ? this._$AH.call(this.options?.host ?? this.element, t) : this._$AH.handleEvent(t);
    }
}
class $d33ef1320595a3ac$var$Z {
    constructor(t, i, s){
        this.element = t, this.type = 6, this._$AN = void 0, this._$AM = i, this.options = s;
    }
    get _$AU() {
        return this._$AM._$AU;
    }
    _$AI(t) {
        $d33ef1320595a3ac$var$M(this, t);
    }
}
const $d33ef1320595a3ac$export$8613d1ca9052b22e = {
    M: $d33ef1320595a3ac$var$h,
    P: $d33ef1320595a3ac$var$o,
    A: $d33ef1320595a3ac$var$n,
    C: 1,
    L: $d33ef1320595a3ac$var$N,
    R: $d33ef1320595a3ac$var$R,
    D: $d33ef1320595a3ac$var$d,
    V: $d33ef1320595a3ac$var$M,
    I: $d33ef1320595a3ac$var$k,
    H: $d33ef1320595a3ac$var$H,
    N: $d33ef1320595a3ac$var$L,
    U: $d33ef1320595a3ac$var$z,
    B: $d33ef1320595a3ac$var$I,
    F: $d33ef1320595a3ac$var$Z
}, $d33ef1320595a3ac$var$B = $d33ef1320595a3ac$var$t.litHtmlPolyfillSupport;
$d33ef1320595a3ac$var$B?.($d33ef1320595a3ac$var$S, $d33ef1320595a3ac$var$k), ($d33ef1320595a3ac$var$t.litHtmlVersions ??= []).push("3.3.2");
const $d33ef1320595a3ac$export$b3890eb0ae9dca99 = (t, i, s)=>{
    const e = s?.renderBefore ?? i;
    let h = e._$litPart$;
    if (void 0 === h) {
        const t = s?.renderBefore ?? null;
        e._$litPart$ = h = new $d33ef1320595a3ac$var$k(i.insertBefore($d33ef1320595a3ac$var$c(), t), t, void 0, s ?? {});
    }
    return h._$AI(t), h;
};




/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */ const $528e4332d1e3099e$var$s = globalThis;
class $528e4332d1e3099e$export$3f2f9f5909897157 extends (0, $375b48187e686ca2$export$c7c07a37856565d) {
    constructor(){
        super(...arguments), this.renderOptions = {
            host: this
        }, this._$Do = void 0;
    }
    createRenderRoot() {
        const t = super.createRenderRoot();
        return this.renderOptions.renderBefore ??= t.firstChild, t;
    }
    update(t) {
        const r = this.render();
        this.hasUpdated || (this.renderOptions.isConnected = this.isConnected), super.update(t), this._$Do = (0, $d33ef1320595a3ac$export$b3890eb0ae9dca99)(r, this.renderRoot, this.renderOptions);
    }
    connectedCallback() {
        super.connectedCallback(), this._$Do?.setConnected(!0);
    }
    disconnectedCallback() {
        super.disconnectedCallback(), this._$Do?.setConnected(!1);
    }
    render() {
        return 0, $d33ef1320595a3ac$export$9c068ae9cc5db4e8;
    }
}
$528e4332d1e3099e$export$3f2f9f5909897157._$litElement$ = !0, $528e4332d1e3099e$export$3f2f9f5909897157["finalized"] = !0, $528e4332d1e3099e$var$s.litElementHydrateSupport?.({
    LitElement: $528e4332d1e3099e$export$3f2f9f5909897157
});
const $528e4332d1e3099e$var$o = $528e4332d1e3099e$var$s.litElementPolyfillSupport;
$528e4332d1e3099e$var$o?.({
    LitElement: $528e4332d1e3099e$export$3f2f9f5909897157
});
const $528e4332d1e3099e$export$f5c524615a7708d6 = {
    _$AK: (t, e, r)=>{
        t._$AK(e, r);
    },
    _$AL: (t)=>t._$AL
};
($528e4332d1e3099e$var$s.litElementVersions ??= []).push("4.2.2");


/**
 * @license
 * Copyright 2022 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */ const $56239b0c931b817c$export$6acf61af03e62db = !1;




var $43a89528e95f706e$exports = {};
$43a89528e95f706e$exports = "ha-card {\n  min-height: 500px;\n  font-family: var(--paper-font-body1_-_font-family, var(--ha-font-family-body, -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, sans-serif));\n  color: var(--primary-text-color, #fff);\n  overflow: hidden;\n  container-type: inline-size;\n}\n\n:host {\n  --ps-text-dim: var(--secondary-text-color, #ffffff80);\n  --ps-text-dimmer: var(--disabled-text-color, #ffffff59);\n  --ps-text-dimmest: var(--disabled-text-color, #ffffff40);\n  --ps-border: var(--divider-color, #ffffff0a);\n  --ps-track: var(--divider-color, #ffffff0f);\n  --ps-card-bg: var(--ha-card-background, var(--card-background-color, #1c1c1c));\n  --ps-elevated: color-mix(in srgb, var(--primary-text-color, #fff) 6%, var(--ps-card-bg));\n}\n\n.card-header {\n  border-bottom: 1px solid var(--divider-color, #e5e7eb);\n  justify-content: space-between;\n  align-items: center;\n  padding: 16px 18px 12px;\n  display: flex;\n}\n\n.header-title {\n  cursor: pointer;\n  align-items: baseline;\n  gap: 7px;\n  min-width: 0;\n  display: flex;\n  overflow: hidden;\n}\n\n.header-title h2 {\n  white-space: nowrap;\n  text-overflow: ellipsis;\n  letter-spacing: -.01em;\n  margin: 0;\n  font-size: 15px;\n  font-weight: 700;\n  overflow: hidden;\n}\n\n.header-sub {\n  color: var(--secondary-text-color);\n  white-space: nowrap;\n  text-overflow: ellipsis;\n  font-size: 12px;\n  font-weight: 400;\n  overflow: hidden;\n}\n\n.header-icons {\n  flex-shrink: 0;\n  align-items: center;\n  gap: 10px;\n  display: flex;\n}\n\n.conn-icon {\n  width: 18px;\n  height: 18px;\n  color: var(--primary-color, #3b82f6);\n  fill: currentColor;\n  cursor: pointer;\n  opacity: 1;\n  transition: color .4s, opacity .4s;\n}\n\n.conn-icon.disconnected {\n  color: var(--disabled-text-color, #9ca3af);\n  opacity: .3;\n}\n\n.more-info-btn {\n  cursor: pointer;\n  opacity: .5;\n  width: 18px;\n  height: 18px;\n  transition: opacity .2s;\n  color: var(--secondary-text-color) !important;\n}\n\n.more-info-btn:hover {\n  opacity: 1;\n}\n\n.notification-banner {\n  background: #ff98001f;\n  border: 1px solid #ff98004d;\n  border-radius: 8px;\n  flex-direction: column;\n  gap: 4px;\n  margin: 8px 14px 4px;\n  padding: 8px 12px;\n  display: flex;\n}\n\n.notification-item {\n  color: #ff9800;\n  align-items: center;\n  gap: 8px;\n  font-size: 13px;\n  display: flex;\n}\n\n.notification-item svg {\n  fill: #ff9800;\n  flex-shrink: 0;\n  width: 18px;\n  height: 18px;\n}\n\n.notification-text {\n  cursor: pointer;\n  flex: 1;\n}\n\n.notification-clear {\n  cursor: pointer;\n  opacity: .6;\n  align-items: center;\n  padding: 2px;\n  transition: opacity .2s;\n  display: flex;\n}\n\n.notification-clear:hover {\n  opacity: 1;\n}\n\n.notification-clear svg {\n  fill: #ff9800;\n  width: 14px;\n  height: 14px;\n}\n\n.chips-row {\n  grid-template-columns: repeat(auto-fit, minmax(0, 1fr));\n  gap: 8px;\n  padding: 12px 14px;\n  display: grid;\n}\n\n.chip {\n  background: var(--card-background-color, #f9fafb);\n  border: 1px solid var(--divider-color, #e5e7eb);\n  cursor: pointer;\n  border-radius: 10px;\n  grid-template-rows: auto auto;\n  grid-template-columns: auto 1fr;\n  align-items: center;\n  column-gap: 8px;\n  min-width: 0;\n  padding: 8px 10px;\n  display: grid;\n}\n\n.chip-icon {\n  flex-shrink: 0;\n  grid-row: 1 / 3;\n  width: 36px;\n  height: 36px;\n  position: relative;\n}\n\n.chip-ring-svg {\n  width: 36px;\n  height: 36px;\n}\n\n.chip-ring-icon {\n  width: 14px;\n  height: 14px;\n  position: absolute;\n  top: 50%;\n  left: 50%;\n  transform: translate(-50%, -50%);\n}\n\n.chip-label {\n  color: var(--secondary-text-color, #6b7280);\n  text-transform: uppercase;\n  letter-spacing: .06em;\n  font-size: 9px;\n  font-weight: 600;\n  line-height: 1;\n}\n\n.chip-value {\n  font-variant-numeric: tabular-nums;\n  font-size: 15px;\n  font-weight: 700;\n  line-height: 1;\n}\n\n.visual-area {\n  flex-direction: column;\n  align-items: center;\n  padding: 4px 14px 0;\n  display: flex;\n}\n\n.gauge-svg {\n  max-width: 100%;\n  height: auto;\n  display: block;\n}\n\n.gauge-status {\n  color: var(--ps-text-dimmest);\n  text-align: center;\n  margin-top: -2px;\n  margin-bottom: 8px;\n  font-size: 13px;\n  transition: color .3s;\n}\n\n.pressure-label {\n  text-align: center;\n  margin-top: -6px;\n  margin-bottom: 2px;\n  font-size: 17px;\n  font-weight: 700;\n  transition: color .3s;\n}\n\n.pressure-value {\n  color: var(--ps-text-dimmest);\n  text-align: center;\n  font-variant-numeric: tabular-nums;\n  margin-bottom: 8px;\n  font-size: 11px;\n}\n\n.gauge-arc-fill {\n  transition: stroke-dashoffset .8s cubic-bezier(.4, 0, .2, 1), stroke .4s;\n}\n\n.zone-arc {\n  stroke-linecap: butt;\n}\n\n.zone-separator {\n  stroke: var(--ps-card-bg);\n  stroke-width: 3px;\n}\n\n.needle-line {\n  stroke-linecap: round;\n  transition: x2 .5s cubic-bezier(.4, 0, .2, 1), y2 .5s cubic-bezier(.4, 0, .2, 1), stroke .3s;\n}\n\n.needle-glow {\n  filter: blur(4px);\n  opacity: .5;\n  transition: x2 .5s cubic-bezier(.4, 0, .2, 1), y2 .5s cubic-bezier(.4, 0, .2, 1), stroke .3s;\n}\n\n.gauge-edge-label {\n  fill: var(--ps-text-dimmest);\n  font-size: 10px;\n}\n\n.shave-stats {\n  justify-content: center;\n  gap: 6px;\n  padding: 8px 14px;\n  display: flex;\n}\n\n.shave-stat-tile {\n  background: var(--ps-elevated);\n  border: 1px solid var(--divider-color, #ffffff0f);\n  text-align: center;\n  border-radius: 10px;\n  flex: 1;\n  min-width: 0;\n  padding: 10px 4px;\n}\n\n.shave-stat-val {\n  font-variant-numeric: tabular-nums;\n  font-size: 15px;\n  font-weight: 700;\n}\n\n.shave-stat-label {\n  color: var(--ps-text-dimmest);\n  margin-top: 6px;\n  font-size: 10px;\n}\n\n.divider {\n  background: var(--ps-border);\n  height: 1px;\n  margin: 0 14px;\n}\n\n.stats {\n  padding: 6px 14px 10px;\n}\n\n.stat-row {\n  border-bottom: 1px solid var(--ps-border);\n  justify-content: space-between;\n  align-items: center;\n  padding: 9px 0;\n  display: flex;\n}\n\n.stat-row:last-child {\n  border-bottom: none;\n}\n\n.stat-label {\n  color: var(--ps-text-dim);\n  align-items: center;\n  gap: 10px;\n  font-size: 13px;\n  display: flex;\n}\n\n.stat-icon {\n  opacity: .55;\n  width: 16px;\n  height: 16px;\n}\n\n.stat-value {\n  color: var(--primary-text-color);\n  font-variant-numeric: tabular-nums;\n  font-size: 13px;\n  font-weight: 600;\n}\n\n.stat-unit {\n  color: var(--ps-text-dimmer);\n  margin-left: 2px;\n  font-size: 11px;\n  font-weight: 400;\n}\n\n.unavailable {\n  text-align: center;\n  color: var(--ps-text-dim);\n  padding: 20px;\n  font-size: 14px;\n}\n\n@container (width <= 350px) {\n  .chip-label, .chip-value {\n    display: none;\n  }\n\n  .chip {\n    grid-template-columns: auto;\n    justify-items: center;\n    padding: 6px;\n  }\n\n  .chip-icon {\n    grid-row: 1;\n  }\n}\n\n.cleaning-wrap {\n  flex-direction: column;\n  align-items: center;\n  padding: 10px 0 4px;\n  display: flex;\n  position: relative;\n}\n\n.cleaning-gauge-ring {\n  width: 160px;\n  height: 160px;\n  position: relative;\n}\n\n.cleaning-ring-svg {\n  width: 160px;\n  height: 160px;\n}\n\n.cleaning-arc-fill {\n  transition: stroke-dashoffset 1s;\n  animation: 2.5s ease-in-out infinite cleanPulse;\n}\n\n@keyframes cleanPulse {\n  0%, 100% {\n    opacity: .7;\n  }\n\n  50% {\n    opacity: 1;\n  }\n}\n\n.cleaning-center {\n  text-align: center;\n  position: absolute;\n  top: 50%;\n  left: 50%;\n  transform: translate(-50%, -50%);\n}\n\n.cleaning-pct {\n  font-variant-numeric: tabular-nums;\n  color: var(--primary-text-color);\n  font-size: 32px;\n  font-weight: 700;\n  line-height: 1;\n}\n\n.cleaning-label {\n  color: #42a5f5;\n  margin-top: 3px;\n  font-size: 11px;\n  font-weight: 500;\n}\n\n.cleaning-droplets {\n  pointer-events: none;\n  width: 160px;\n  height: 160px;\n  position: absolute;\n  top: 0;\n  left: 0;\n}\n\n.droplet {\n  opacity: 0;\n  background: #42a5f5;\n  border-radius: 50% 50% 50% 0;\n  animation: linear infinite dropletFall;\n  position: absolute;\n  transform: rotate(-45deg);\n}\n\n@keyframes dropletFall {\n  0% {\n    opacity: 0;\n    transform: rotate(-45deg)translateY(0)scale(1);\n  }\n\n  15% {\n    opacity: .6;\n  }\n\n  85% {\n    opacity: .3;\n  }\n\n  100% {\n    opacity: 0;\n    transform: rotate(-45deg)translateY(70px)scale(.4);\n  }\n}\n\n.cleaning-status {\n  color: #42a5f5;\n  align-items: center;\n  gap: 6px;\n  margin-top: 6px;\n  font-size: 13px;\n  display: flex;\n}\n\n.clean-spinner {\n  border: 2px solid #42a5f5;\n  border-top-color: #0000;\n  border-radius: 50%;\n  width: 14px;\n  height: 14px;\n  animation: 1s linear infinite spinClean;\n}\n\n@keyframes spinClean {\n  100% {\n    transform: rotate(360deg);\n  }\n}\n\n.battery-wrap {\n  flex-direction: column;\n  align-items: center;\n  padding: 12px 0 4px;\n  display: flex;\n}\n\n.battery-container {\n  width: 200px;\n  height: 100px;\n  position: relative;\n}\n\n.battery-body {\n  border: 3px solid var(--secondary-text-color, #ffffff80);\n  background: var(--ps-elevated);\n  border-radius: 8px;\n  width: 180px;\n  height: 100px;\n  position: absolute;\n  top: 0;\n  left: 0;\n  overflow: hidden;\n}\n\n.battery-cap {\n  border: 3px solid var(--secondary-text-color, #ffffff80);\n  background: var(--ps-card-bg);\n  border-left: none;\n  border-radius: 0 5px 5px 0;\n  width: 14px;\n  height: 40px;\n  position: absolute;\n  top: 50%;\n  right: 0;\n  transform: translateY(-50%);\n}\n\n.battery-liquid {\n  opacity: .75;\n  background: #4caf50;\n  transition: width 1s;\n  position: absolute;\n  top: 0;\n  bottom: 0;\n  left: 0;\n  overflow: hidden;\n}\n\n.battery-wave-surface {\n  width: 14px;\n  position: absolute;\n  top: 0;\n  bottom: 0;\n  right: -7px;\n  overflow: hidden;\n}\n\n.battery-wave-inner {\n  width: 14px;\n  height: 200%;\n  animation: 2s linear infinite waveVert;\n}\n\n@keyframes waveVert {\n  0% {\n    transform: translateY(0);\n  }\n\n  100% {\n    transform: translateY(-50%);\n  }\n}\n\n.battery-bubbles {\n  pointer-events: none;\n  position: absolute;\n  inset: 0;\n  overflow: hidden;\n}\n\n.bubble {\n  background: #ffffff59;\n  border-radius: 50%;\n  animation: linear infinite bubbleRise;\n  position: absolute;\n}\n\n@keyframes bubbleRise {\n  0% {\n    opacity: .5;\n    transform: translateX(0)scale(1);\n  }\n\n  100% {\n    opacity: 0;\n    transform: translateX(60px)translateY(-10px)scale(.3);\n  }\n}\n\n.battery-bolt {\n  z-index: 2;\n  position: absolute;\n  top: 50%;\n  left: 50%;\n  transform: translate(-50%, -50%);\n}\n\n.battery-bolt svg {\n  filter: drop-shadow(0 1px 4px #00000026);\n  width: 36px;\n  height: 36px;\n  animation: 2s ease-in-out infinite boltPulse;\n}\n\n@keyframes boltPulse {\n  0%, 100% {\n    opacity: .7;\n    transform: scale(1);\n  }\n\n  50% {\n    opacity: 1;\n    transform: scale(1.08);\n  }\n}\n\n.battery-pct {\n  font-variant-numeric: tabular-nums;\n  color: var(--primary-text-color);\n  text-align: center;\n  margin-top: 10px;\n  font-size: 36px;\n  font-weight: 700;\n}\n\n.battery-sub {\n  color: #4caf50;\n  text-align: center;\n  justify-content: center;\n  align-items: center;\n  gap: 4px;\n  margin-top: 2px;\n  font-size: 12px;\n  display: flex;\n}\n\n.charge-dot {\n  background: #4caf50;\n  border-radius: 50%;\n  width: 5px;\n  height: 5px;\n  display: inline-block;\n}\n\n.charge-dot:first-child {\n  animation: 1.4s infinite chDot;\n}\n\n.charge-dot:nth-child(2) {\n  animation: 1.4s .2s infinite chDot;\n}\n\n.charge-dot:nth-child(3) {\n  animation: 1.4s .4s infinite chDot;\n}\n\n@keyframes chDot {\n  0%, 80%, 100% {\n    opacity: .2;\n    transform: scale(.7);\n  }\n\n  40% {\n    opacity: 1;\n    transform: scale(1.1);\n  }\n}\n\n.init-wrap {\n  flex-direction: column;\n  justify-content: center;\n  align-items: center;\n  display: flex;\n  overflow: hidden;\n}\n\n.init-rings {\n  flex-shrink: 0;\n  justify-content: center;\n  align-items: center;\n  width: 180px;\n  height: 180px;\n  display: flex;\n  position: relative;\n}\n\n.init-ring {\n  border: 2px solid var(--primary-color, #3b82f6);\n  opacity: 0;\n  border-radius: 50%;\n  animation: 3s ease-out infinite initPulse;\n  position: absolute;\n}\n\n.init-ring-1 {\n  width: 70px;\n  height: 70px;\n  animation-delay: 0s;\n}\n\n.init-ring-2 {\n  width: 70px;\n  height: 70px;\n  animation-delay: 1s;\n}\n\n.init-ring-3 {\n  width: 70px;\n  height: 70px;\n  animation-delay: 2s;\n}\n\n@keyframes initPulse {\n  0% {\n    opacity: .6;\n    width: 70px;\n    height: 70px;\n  }\n\n  100% {\n    opacity: 0;\n    width: 190px;\n    height: 190px;\n  }\n}\n\n.init-bt {\n  z-index: 1;\n  width: 52px;\n  height: 52px;\n  animation: 2s ease-in-out infinite initBtPulse;\n  position: relative;\n}\n\n.init-bt svg {\n  width: 52px;\n  height: 52px;\n}\n\n@keyframes initBtPulse {\n  0%, 100% {\n    opacity: .5;\n    transform: scale(.95);\n  }\n\n  50% {\n    opacity: 1;\n    transform: scale(1.05);\n  }\n}\n\n.init-label {\n  color: var(--primary-color, #3b82f6);\n  margin-top: 6px;\n  margin-bottom: 8px;\n  font-size: 13px;\n  font-weight: 500;\n}\n\n@keyframes chargeGlow {\n  0%, 100% {\n    stroke-opacity: .3;\n  }\n\n  50% {\n    stroke-opacity: 1;\n  }\n}\n\n.charging-arc {\n  animation: 2s ease-in-out infinite chargeGlow;\n}\n";


var $76eee68ef692a3c3$exports = {};
$76eee68ef692a3c3$exports = JSON.parse('{"chip_battery":"Battery","chip_head":"Head","chip_clean":"Clean","gauge_session":"SESSION","gauge_battery":"Battery","gauge_standby":"Standby","gauge_initializing":"Connecting\u2026","gauge_charging":"Charging","gauge_cleaning":"Cleaning","gauge_in_progress":"In Progress","gauge_low":"Low","gauge_high":"High","gauge_slow":"Slow","gauge_fast":"Fast","pressure_no_contact":"No Contact","pressure_too_low":"Too Low","pressure_optimal":"Optimal","pressure_too_high":"Too High","speed_none":"No Movement","speed_optimal":"Optimal","speed_too_fast":"Too Fast","motion_small_circle":"Circles","motion_large_stroke":"Strokes","stat_charge_cycles":"Charge Cycles","stat_last_session":"Last Session","stat_last_used":"Last Used","stat_total_time":"Total Time","stat_total_uses":"Total Uses","stat_cycles_remaining":"Cycles Remaining","shave_rpm":"RPM","shave_ma":"mA","shave_speed":"Speed","shave_motion":"Motion","time_today":"Today","time_yesterday":"Yesterday","time_days_ago":"{n}d ago","notif_notification_motor_blocked":"Motor Blocked","notif_notification_clean_reminder":"Cleaning Required","notif_notification_head_replacement":"Replace Shaving Head","notif_notification_battery_overheated":"Battery Overheated","notif_notification_unplug_required":"Unplug Before Use","config_title":"Title (Optional)","config_show_model":"Show model number as subtitle","config_select_device":"Please select a Philips Shaver device in the card configuration.","config_no_device":"Please select a device.","default_title":"Philips Shaver","outdated_standalone_active":"An outdated standalone copy of this card is active. Remove the standalone Philips Shaver Card (see Settings \u2192 Repairs) to use the up-to-date version bundled with the integration."}');


var $238d401f28c1db46$exports = {};
$238d401f28c1db46$exports = JSON.parse('{"chip_battery":"Akku","chip_head":"Scherkopf","chip_clean":"Reinigung","gauge_session":"SITZUNG","gauge_battery":"Akku","gauge_standby":"Bereit","gauge_initializing":"Verbinde\u2026","gauge_charging":"Laden","gauge_cleaning":"Reinigung","gauge_in_progress":"L\xe4uft","gauge_low":"Niedrig","gauge_high":"Hoch","gauge_slow":"Langsam","gauge_fast":"Schnell","pressure_no_contact":"Kein Kontakt","pressure_too_low":"Zu niedrig","pressure_optimal":"Optimal","pressure_too_high":"Zu hoch","speed_none":"Keine Bewegung","speed_optimal":"Optimal","speed_too_fast":"Zu schnell","motion_small_circle":"Kreise","motion_large_stroke":"Z\xfcge","stat_charge_cycles":"Ladezyklen","stat_last_session":"Letzte Sitzung","stat_last_used":"Zuletzt benutzt","stat_total_time":"Gesamtzeit","stat_total_uses":"Nutzungen","stat_cycles_remaining":"Zyklen \xfcbrig","shave_rpm":"U/min","shave_ma":"mA","shave_speed":"Tempo","shave_motion":"Bewegung","time_today":"Heute","time_yesterday":"Gestern","time_days_ago":"vor {n} T.","notif_notification_motor_blocked":"Motor blockiert","notif_notification_clean_reminder":"Reinigung f\xe4llig","notif_notification_head_replacement":"Scherkopf wechseln","notif_notification_battery_overheated":"Akku \xfcberhitzt","notif_notification_unplug_required":"Ausstecken erforderlich","config_title":"Titel (Optional)","config_show_model":"Modellnummer als Untertitel anzeigen","config_select_device":"Bitte w\xe4hle einen Philips Shaver in der Kartenkonfiguration.","config_no_device":"Bitte w\xe4hle ein Ger\xe4t.","default_title":"Philips Shaver","outdated_standalone_active":"Eine veraltete separate Kopie dieser Karte ist aktiv. Entferne die separate Philips Shaver Card (siehe Einstellungen \u2192 Reparaturen), um die aktuelle, mit der Integration gelieferte Version zu nutzen."}');


const $d8078e452c66bdbe$var$LOCALES = {
    en: (/*@__PURE__*/$parcel$interopDefault($76eee68ef692a3c3$exports)),
    de: (/*@__PURE__*/$parcel$interopDefault($238d401f28c1db46$exports))
};
function $d8078e452c66bdbe$export$625550452a3fa3ec(hass, key) {
    const lang = hass?.language || 'en';
    const locale = $d8078e452c66bdbe$var$LOCALES[lang] || $d8078e452c66bdbe$var$LOCALES.en;
    return locale[key] || $d8078e452c66bdbe$var$LOCALES.en[key] || key;
}


// Written by the release sync script (philips_shaver scripts/sync_card.sh).
const $8ee5ce714273e53b$export$d5e7ce6d07daf10f = "0.20.0";
const $8ee5ce714273e53b$export$9b657414b7dffe40 = "bundled";


// ---------- Entity discovery map: translation_key → local alias ----------
const $8b62e546fdd14731$var$TRANSLATION_KEY_MAP = {
    battery: "battery",
    activity: "activity",
    device_state: "device_state",
    shaving_time: "shaving_time",
    head_remaining: "head_remaining",
    motor_rpm: "motor_rpm",
    motor_current: "motor_current",
    motor_current_max: "motor_current_max",
    pressure: "pressure",
    pressure_state: "pressure_state",
    days_last_used: "days_last_used",
    cleaning_cycles: "cleaning_cycles",
    total_age: "total_age",
    amount_of_charges: "amount_of_charges",
    amount_of_operational_turns: "amount_of_operational_turns",
    model_number: "model_number",
    firmware: "firmware",
    rssi: "rssi",
    last_seen: "last_seen",
    handle_load_type: "handle_load_type",
    motion_type: "motion_type",
    cleaning_progress: "cleaning_progress",
    cleaning_cycles_remaining: "cleaning_cycles_remaining",
    charging: "is_charging",
    travel_lock: "travel_lock",
    esp_bridge_alive: "esp_bridge_alive",
    shaver_ble_connected: "shaver_ble_connected",
    shaving_mode: "shaving_mode",
    lightring_brightness: "lightring_brightness",
    speed: "speed",
    speed_verdict: "speed_verdict",
    notification_motor_blocked: "notification_motor_blocked",
    notification_clean_reminder: "notification_clean_reminder",
    notification_head_replacement: "notification_head_replacement",
    notification_battery_overheated: "notification_battery_overheated",
    notification_unplug_required: "notification_unplug_required"
};
const $8b62e546fdd14731$var$NOTIFICATIONS = [
    {
        key: "notification_motor_blocked",
        icon: "engine_off"
    },
    {
        key: "notification_clean_reminder",
        icon: "spray"
    },
    {
        key: "notification_head_replacement",
        icon: "razor"
    },
    {
        key: "notification_battery_overheated",
        icon: "thermometer"
    },
    {
        key: "notification_unplug_required",
        icon: "plug_off"
    }
];
// ---------- Gauge constants ----------
const $8b62e546fdd14731$var$GAUGE = {
    CX: 140,
    CY: 142,
    R: 108,
    STROKE: 22,
    PRESSURE_MAX: 6000,
    ZONE_BASE: 500 / 6000,
    ZONE_LOW: 0.25,
    ZONE_HIGH: 4000 / 6000,
    SPEED_MAX: 300,
    SPEED_ZONE_OPTIMAL: 0.5
};
const $8b62e546fdd14731$var$GAUGE_W = 280;
// ---------- SVG arc helpers (semicircle, CW in SVG) ----------
function $8b62e546fdd14731$var$fracToXY(frac, r = $8b62e546fdd14731$var$GAUGE.R) {
    const deg = 180 + 180 * frac;
    const rad = deg * Math.PI / 180;
    return {
        x: $8b62e546fdd14731$var$GAUGE.CX + r * Math.cos(rad),
        y: $8b62e546fdd14731$var$GAUGE.CY + r * Math.sin(rad)
    };
}
function $8b62e546fdd14731$var$describeArc(f1, f2, r = $8b62e546fdd14731$var$GAUGE.R) {
    const range = 180;
    const spanDeg = (f2 - f1) * range;
    let ef1 = f1, ef2 = f2;
    if (f2 - f1 >= 0.999) {
        ef1 = 0.001;
        ef2 = 0.999;
    }
    const p1 = $8b62e546fdd14731$var$fracToXY(ef1, r), p2 = $8b62e546fdd14731$var$fracToXY(ef2, r);
    const large = spanDeg > 180 ? 1 : 0;
    return `M ${p1.x} ${p1.y} A ${r} ${r} 0 ${large} 1 ${p2.x} ${p2.y}`;
}
// ---------- Mini ring arc helper (270° arc, gap at bottom, CW in SVG) ----------
const $8b62e546fdd14731$var$RING = {
    CX: 18,
    CY: 18,
    R: 14,
    SW: 3,
    START: 135,
    END: 405
};
function $8b62e546fdd14731$var$ringArc(frac) {
    const f = Math.max(0, Math.min(1, frac));
    const range = $8b62e546fdd14731$var$RING.END - $8b62e546fdd14731$var$RING.START;
    const startRad = $8b62e546fdd14731$var$RING.START * Math.PI / 180;
    const endRad = ($8b62e546fdd14731$var$RING.START + range * f) * Math.PI / 180;
    const x1 = $8b62e546fdd14731$var$RING.CX + $8b62e546fdd14731$var$RING.R * Math.cos(startRad);
    const y1 = $8b62e546fdd14731$var$RING.CY + $8b62e546fdd14731$var$RING.R * Math.sin(startRad);
    const x2 = $8b62e546fdd14731$var$RING.CX + $8b62e546fdd14731$var$RING.R * Math.cos(endRad);
    const y2 = $8b62e546fdd14731$var$RING.CY + $8b62e546fdd14731$var$RING.R * Math.sin(endRad);
    const large = range * f > 180 ? 1 : 0;
    return `M ${x1} ${y1} A ${$8b62e546fdd14731$var$RING.R} ${$8b62e546fdd14731$var$RING.R} 0 ${large} 1 ${x2} ${y2}`;
}
function $8b62e546fdd14731$var$ringBgArc() {
    return $8b62e546fdd14731$var$ringArc(1);
}
// ---------- Formatting helpers ----------
function $8b62e546fdd14731$var$formatAge(s) {
    const d = Math.floor(s / 86400);
    const h = Math.floor(s % 86400 / 3600);
    return `${d}d ${h}h`;
}
function $8b62e546fdd14731$var$formatSession(s) {
    return `${Math.floor(s / 60)}m ${s % 60}s`;
}
const $8b62e546fdd14731$var$DISABLED_COLOR = "var(--disabled-text-color, #9e9e9e)";
function $8b62e546fdd14731$var$batteryColor(pct) {
    if (pct <= 0) return $8b62e546fdd14731$var$DISABLED_COLOR;
    if (pct > 50) return "#4caf50";
    if (pct > 20) return "#ff9800";
    return "#f44336";
}
function $8b62e546fdd14731$var$headColor(pct) {
    if (pct <= 0) return $8b62e546fdd14731$var$DISABLED_COLOR;
    if (pct > 30) return "#3f51b5";
    if (pct > 15) return "#ff9800";
    return "#f44336";
}
function $8b62e546fdd14731$var$cleaningColor(remaining) {
    if (remaining <= 0) return $8b62e546fdd14731$var$DISABLED_COLOR;
    if (remaining > 15) return "#00bcd4";
    if (remaining > 5) return "#ff9800";
    return "#f44336";
}
// ---------- SVG Icon paths ----------
const $8b62e546fdd14731$var$ICONS = {
    speed: 'M12 16a3 3 0 0 1-2.12-.88L4.93 10.2a8 8 0 1 1 14.14 0l-4.95 4.95A3 3 0 0 1 12 16zm0-12a6 6 0 0 0-4.24 10.24L12 18.49l4.24-4.25A6 6 0 0 0 12 4z',
    current: 'M7 2v11h3v9l7-12h-4l4-8z',
    clock: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 18a8 8 0 1 1 0-16 8 8 0 0 1 0 16zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z',
    calendar: 'M19 3h-1V1h-2v2H8V1H6v2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2zm0 16H5V8h14z',
    clean: 'M16 11h-1V3a2 2 0 0 0-2-2h-2a2 2 0 0 0-2 2v8H8a5 5 0 0 0-5 5v5a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1v-5a5 5 0 0 0-5-5z',
    counter: 'M4 4h16v16H4V4zm2 2v12h12V6H6zm3 3h2v2H9V9zm0 4h6v2H9v-2zm4-4h2v2h-2V9z',
    signal: 'M12 6c3.33 0 6 2.67 6 6h2c0-4.42-3.58-8-8-8S4 7.58 4 12h2c0-3.33 2.67-6 6-6zm0 4c1.1 0 2 .9 2 2h2a4 4 0 0 0-8 0h2c0-1.1.9-2 2-2zm-1 4h2v2h-2z',
    firmware: 'M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6z',
    lock: 'M18 8h-1V6a5 5 0 0 0-10 0v2H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V10a2 2 0 0 0-2-2zm-6 9a2 2 0 1 1 0-4 2 2 0 0 1 0 4zM9 8V6a3 3 0 0 1 6 0v2H9z',
    charge: 'M15.67 4H14V2h-4v2H8.33A1.33 1.33 0 0 0 7 5.33v15.34C7 21.4 7.6 22 8.33 22h7.34c.74 0 1.33-.6 1.33-1.33V5.33C17 4.6 16.4 4 15.67 4zM11 20v-5.5H9L13 7v5.5h2L11 20z',
    bluetooth: 'M17.71 7.71L12 2h-1v7.59L6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 11 14.41V22h1l5.71-5.71-4.3-4.29 4.3-4.29zM13 5.83l1.88 1.88L13 9.59V5.83zm1.88 10.46L13 18.17v-3.76l1.88 1.88z',
    lan_connect: 'M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z',
    lan_disconnect: 'M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM17 7h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z',
    razor: 'M20 8C19.45 8 19 7.55 19 7C19 6.45 19.45 6 20 6V5H4V6C4.55 6 5 6.45 5 7C5 7.55 4.55 8 4 8H2V15H4C4.55 15 5 15.45 5 16C5 16.55 4.55 17 4 17V18H20V17C19.45 17 19 16.55 19 16C19 15.45 19.45 15 20 15H22V8H20M20 12H19V13H17V12H13.41C13.2 12.58 12.65 13 12 13S10.8 12.58 10.59 12H7V13H5V12H4V11H5V10H7V11H10.59C10.8 10.42 11.35 10 12 10S13.2 10.42 13.41 11H17V10H19V11H20V12Z',
    droplet: 'M12 2c0 0-6 7.34-6 11a6 6 0 0 0 12 0c0-3.66-6-11-6-11zm0 15a3 3 0 0 1-3-3c0-.55.45-1 1-1s1 .45 1 1a1 1 0 0 0 1 1c.55 0 1 .45 1 1s-.45 1-1 1z',
    motor: 'M13 2.05v3.03c3.39.49 6 3.39 6 6.92 0 .9-.18 1.75-.48 2.54l2.6 1.53c.56-1.24.88-2.62.88-4.07 0-5.18-3.95-9.45-9-9.95zM12 19c-3.87 0-7-3.13-7-7 0-3.53 2.61-6.43 6-6.92V2.05c-5.06.5-9 4.76-9 9.95 0 5.52 4.47 10 9.99 10 3.31 0 6.24-1.61 8.06-4.09l-2.6-1.53A6.95 6.95 0 0 1 12 19z',
    charges: 'M15.67 4H14V2h-4v2H8.33A1.33 1.33 0 0 0 7 5.33v15.34C7 21.4 7.6 22 8.33 22h7.34c.74 0 1.33-.6 1.33-1.33V5.33C17 4.6 16.4 4 15.67 4z',
    alert: 'M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z',
    close: 'M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z',
    engine_off: 'M11 8h2v4.17l2 2V8h4v6.17l1.78 1.78c.14-.62.22-1.27.22-1.95 0-4.42-3.58-8-8-8-1.57 0-3.03.47-4.25 1.26L11 9.43V8zM2.81 2.81L1.39 4.22 5.17 8H3v8h4v4h6v-4h.17l4.61 4.61 1.41-1.41L2.81 2.81zM11 18H9v-4H7v-4h.17l3.83 3.83V18z',
    spray: 'M12 2L8 6v2h8V6l-4-4zm-2 5V6.5l2-2 2 2V7h-4zm-3 4h10v9H7v-9zm2 2v5h6v-5H9z',
    thermometer: 'M15 13V5c0-1.66-1.34-3-3-3S9 3.34 9 5v8c-1.21.91-2 2.37-2 4 0 2.76 2.24 5 5 5s5-2.24 5-5c0-1.63-.79-3.09-2-4zm-4-8c0-.55.45-1 1-1s1 .45 1 1v3h-2V5z',
    plug_off: 'M12 2c-1.1 0-2 .9-2 2v2H8v5c0 2.21 1.79 4 4 4s4-1.79 4-4V6h-2V4c0-1.1-.9-2-2-2zm0 14c-4 0-6 2-6 4v1h12v-1c0-2-2-4-6-4z'
};
const $8b62e546fdd14731$var$PRESSURE_COLORS = {
    no_contact: "var(--disabled-text-color, #9e9e9e)",
    too_low: "#42a5f5",
    optimal: "#4caf50",
    too_high: "#f44336"
};
const $8b62e546fdd14731$var$SPEED_COLORS = {
    none: "var(--disabled-text-color, #9e9e9e)",
    optimal: "#4caf50",
    too_fast: "#ff9800"
};
class $8b62e546fdd14731$export$4778d74453ecc150 extends (0, $528e4332d1e3099e$export$3f2f9f5909897157) {
    // ---------- Translation helper ----------
    _t(key) {
        return (0, $d8078e452c66bdbe$export$625550452a3fa3ec)(this._hass, key);
    }
    set hass(hass) {
        this._hass = hass;
        if ((!this._entities || !this._entities.battery) && this.config?.device_id) this._entities = this._findEntities(hass, this.config.device_id);
        // Clear dismissed notifications once the real state catches up
        if (this._dismissed?.size) {
            for (const key of [
                ...this._dismissed
            ])if (this._stateVal(key) !== "on") this._dismissed.delete(key);
        }
        // Timer management
        const activity = this._stateVal("activity", "off");
        if (activity === "shaving" && !this._timer) this._startTimer();
        else if (activity !== "shaving" && this._timer) this._stopTimer();
        this.requestUpdate();
    }
    get hass() {
        return this._hass;
    }
    connectedCallback() {
        super.connectedCallback();
    }
    disconnectedCallback() {
        super.disconnectedCallback();
        this._stopTimer();
    }
    setConfig(config) {
        if (!config.device_id) throw new Error((0, $d8078e452c66bdbe$export$625550452a3fa3ec)(null, "config_select_device"));
        this.config = config;
        this._entities = null;
        if (this._hass) this._entities = this._findEntities(this._hass, config.device_id);
    }
    getCardSize() {
        return 6;
    }
    // ---------- Entity discovery ----------
    _findEntities(hass, deviceId) {
        const allEntities = hass.entities || {};
        const devices = hass.devices || {};
        const found = {};
        const deviceIds = new Set([
            deviceId
        ]);
        const mainDevice = devices[deviceId];
        if (mainDevice) {
            const configEntries = mainDevice.config_entries || [];
            for (const [id, dev] of Object.entries(devices)){
                if (id === deviceId) continue;
                const devEntries = dev.config_entries || [];
                if (configEntries.some((ce)=>devEntries.includes(ce))) deviceIds.add(id);
            }
        }
        for(const entityId in allEntities){
            const entity = allEntities[entityId];
            if (!deviceIds.has(entity.device_id)) continue;
            const tKey = entity.translation_key;
            if (tKey && $8b62e546fdd14731$var$TRANSLATION_KEY_MAP[tKey]) found[$8b62e546fdd14731$var$TRANSLATION_KEY_MAP[tKey]] = entity.entity_id;
            const state = hass.states[entity.entity_id];
            if (!found.battery && state?.attributes?.device_class === "battery") found.battery = entity.entity_id;
        }
        return found;
    }
    // ---------- State helpers ----------
    _entity(key) {
        const id = this._entities?.[key];
        return id ? this._hass.states[id] : null;
    }
    _stateVal(key, fallback) {
        const e = this._entity(key);
        if (!e || e.state === "unavailable" || e.state === "unknown") return fallback !== undefined ? fallback : null;
        return e.state;
    }
    _numState(key, fallback = 0) {
        const v = this._stateVal(key);
        if (v === null) return fallback;
        const n = parseFloat(v);
        return isNaN(n) ? fallback : n;
    }
    // ---------- Timer ----------
    _startTimer() {
        if (this._timer) return;
        this._elapsed = this._numState("shaving_time", 0);
        this._timer = setInterval(()=>{
            this._elapsed++;
            this.requestUpdate();
        }, 1000);
    }
    _stopTimer() {
        if (this._timer) {
            clearInterval(this._timer);
            this._timer = null;
        }
    }
    // ---------- More-info event ----------
    _fireMoreInfo(entityId) {
        if (!entityId) return;
        this.dispatchEvent(new CustomEvent('hass-more-info', {
            bubbles: true,
            composed: true,
            detail: {
                entityId: entityId
            }
        }));
    }
    _navigateToDevice() {
        const deviceId = this.config?.device_id;
        if (!deviceId) return;
        const path = `/config/devices/device/${deviceId}`;
        history.pushState(null, "", path);
        window.dispatchEvent(new CustomEvent("location-changed", {
            detail: {
                replace: false
            }
        }));
    }
    // ---------- SVG icon helper ----------
    _svgIcon(name) {
        return (0, $d33ef1320595a3ac$export$7ed1367e7fa1ad68)`<path d="${$8b62e546fdd14731$var$ICONS[name] || ''}"/>`;
    }
    // ---------- Main render ----------
    render() {
        const hass = this._hass;
        const config = this.config;
        if (!hass || !config || !this._entities) {
            if (hass && config?.device_id) this._entities = this._findEntities(hass, config.device_id);
            if (!this._entities) return (0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`<ha-card><div class="unavailable">${this._t("config_no_device")}</div></ha-card>`;
        }
        const activity = this._stateVal("activity", "off");
        return (0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`
      <ha-card>
        ${this._renderHeader()}
        ${this._renderNotifications()}
        ${this._renderChips()}
        <div class="visual-area">
          ${this._renderGauge(activity)}
        </div>
        <div class="divider"></div>
        ${this._renderStats(activity)}
      </ha-card>
    `;
    }
    // ---------- Header ----------
    _renderHeader() {
        const device = this._hass.devices?.[this.config.device_id];
        const model = device?.model || "";
        // Default the header to the device's name (HA user-rename wins, then the
        // integration-provided friendly_name) so the card matches what the device
        // is actually called; fall back to the generic title only when unnamed.
        const name = this.config.title || device?.name_by_user || device?.name || this._t("default_title");
        const showModel = this.config.show_model !== false;
        const espEntity = this._entity("esp_bridge_alive");
        const espConnected = espEntity ? espEntity.state === "on" : false;
        const bleEntity = this._entity("shaver_ble_connected");
        const bleConnected = bleEntity ? bleEntity.state === "on" : false;
        return (0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`
      <div class="card-header">
        <div class="header-title" @click="${()=>this._fireMoreInfo(this._entities?.activity)}">
          <h2>${name}</h2>
          ${showModel && model ? (0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`<span class="header-sub">${model}</span>` : ''}
        </div>
        <div class="header-icons">
          <svg class="conn-icon ${bleConnected ? '' : 'disconnected'}"
               viewBox="0 0 24 24"
               @click="${()=>this._fireMoreInfo(this._entities?.shaver_ble_connected)}">
            <path d="${$8b62e546fdd14731$var$ICONS.bluetooth}"/>
          </svg>
          ${espEntity ? (0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`
          <svg class="conn-icon ${espConnected ? '' : 'disconnected'}"
               viewBox="0 0 24 24"
               @click="${()=>this._fireMoreInfo(this._entities?.esp_bridge_alive)}">
            <path d="${espConnected ? $8b62e546fdd14731$var$ICONS.lan_connect : $8b62e546fdd14731$var$ICONS.lan_disconnect}"/>
          </svg>` : ''}
          <svg class="more-info-btn" viewBox="0 0 24 24" fill="currentColor" stroke="none"
               @click="${()=>this._navigateToDevice()}">
            <circle cx="12" cy="5" r="1.5"/>
            <circle cx="12" cy="12" r="1.5"/>
            <circle cx="12" cy="19" r="1.5"/>
          </svg>
        </div>
      </div>
    `;
    }
    // ---------- Notification banner ----------
    _renderNotifications() {
        const active = $8b62e546fdd14731$var$NOTIFICATIONS.filter((n)=>this._stateVal(n.key) === "on" && !this._dismissed?.has(n.key));
        if (active.length === 0) return '';
        return (0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`
      <div class="notification-banner">
        ${active.map((n)=>(0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`
          <div class="notification-item">
            <svg viewBox="0 0 24 24"><path d="${$8b62e546fdd14731$var$ICONS.alert}"/></svg>
            <span class="notification-text"
                  @click="${()=>this._fireMoreInfo(this._entities?.[n.key])}"
            >${this._t("notif_" + n.key)}</span>
            <span class="notification-clear"
                  @click="${(e)=>{
                e.stopPropagation();
                this._clearNotification(n.key);
            }}">
              <svg viewBox="0 0 24 24"><path d="${$8b62e546fdd14731$var$ICONS.close}"/></svg>
            </span>
          </div>
        `)}
      </div>
    `;
    }
    _clearNotification(key) {
        if (!this._hass) return;
        if (!this._dismissed) this._dismissed = new Set();
        this._dismissed.add(key);
        this.requestUpdate();
        const device = this._hass.devices?.[this.config.device_id];
        const entryId = device?.config_entries?.[0];
        this._hass.callService("philips_shaver", "acknowledge_notification", {
            notification: key,
            ...entryId ? {
                entry_id: entryId
            } : {}
        });
    }
    // ---------- Chips row ----------
    _renderChips() {
        const bat = this._numState("battery", 0);
        const bc = $8b62e546fdd14731$var$batteryColor(bat);
        const head = this._numState("head_remaining", 0);
        const hc = $8b62e546fdd14731$var$headColor(head);
        const clean = this._numState("cleaning_cycles_remaining", 0);
        const cc = $8b62e546fdd14731$var$cleaningColor(clean);
        const activity = this._stateVal("activity", "off");
        const bg = $8b62e546fdd14731$var$ringBgArc();
        const tiles = [
            {
                key: "battery",
                label: this._t("chip_battery"),
                value: `${bat}%`,
                frac: bat / 100,
                color: bc,
                icon: activity === "charging" ? $8b62e546fdd14731$var$ICONS.charge : $8b62e546fdd14731$var$ICONS.charges,
                entity: this._entities?.battery
            },
            {
                key: "head",
                label: this._t("chip_head"),
                value: `${Math.round(head)}%`,
                frac: head / 100,
                color: hc,
                icon: $8b62e546fdd14731$var$ICONS.razor,
                entity: this._entities?.head_remaining
            }
        ];
        if (this._entities?.cleaning_cycles_remaining) tiles.push({
            key: "cleaning",
            label: this._t("chip_clean"),
            value: clean.toFixed(0),
            frac: clean / 30,
            color: cc,
            icon: $8b62e546fdd14731$var$ICONS.droplet,
            entity: this._entities.cleaning_cycles_remaining
        });
        return (0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`
      <div class="chips-row">
        ${tiles.map((t)=>(0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`
          <div class="chip" @click="${()=>this._fireMoreInfo(t.entity)}">
            <div class="chip-icon">
              <svg class="chip-ring-svg" viewBox="0 0 36 36">
                <path d="${bg}" fill="none" stroke="var(--ps-track)" stroke-width="${$8b62e546fdd14731$var$RING.SW}" stroke-linecap="round"/>
                <path d="${$8b62e546fdd14731$var$ringArc(t.frac)}" fill="none" stroke="${t.color}" stroke-width="${$8b62e546fdd14731$var$RING.SW}" stroke-linecap="round"/>
              </svg>
              <svg class="chip-ring-icon" viewBox="0 0 24 24" fill="${t.color}">
                <path d="${t.icon}"/>
              </svg>
            </div>
            <span class="chip-label">${t.label}</span>
            <span class="chip-value" style="color:${t.color}">${t.value}</span>
          </div>
        `)}
      </div>
    `;
    }
    // ---------- Device type ----------
    get _isOneBlade() {
        return !!this._entities?.speed;
    }
    // ---------- Gauge ----------
    _renderGauge(activity) {
        if (activity === "initializing") return this._renderInitializing();
        if (activity === "shaving") return this._isOneBlade ? this._renderSpeedGauge() : this._renderPressureGauge();
        if (activity === "cleaning") return this._renderCleaningGauge();
        if (activity === "charging") return this._renderChargingBattery();
        return this._renderBatteryGauge();
    }
    _renderInitializing() {
        return (0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`
      <div class="init-wrap">
        <div class="init-rings">
          <div class="init-ring init-ring-1"></div>
          <div class="init-ring init-ring-2"></div>
          <div class="init-ring init-ring-3"></div>
          <div class="init-bt">
            <svg viewBox="0 0 24 24" fill="var(--primary-color, #3b82f6)">
              <path d="${$8b62e546fdd14731$var$ICONS.bluetooth}"/>
            </svg>
          </div>
        </div>
        <div class="init-label">${this._t("gauge_initializing")}</div>
      </div>
    `;
    }
    _renderPressureGauge() {
        const { CX: cx, CY: cy, R: r, STROKE: st, PRESSURE_MAX: max } = $8b62e546fdd14731$var$GAUGE;
        const pressure = this._numState("pressure", 0);
        const pState = this._stateVal("pressure_state", "no_contact");
        const elapsed = this._elapsed || this._numState("shaving_time", 0);
        const tm = Math.floor(elapsed / 60);
        const ts = elapsed % 60;
        const timerStr = String(tm).padStart(2, "0") + ":" + String(ts).padStart(2, "0");
        const needleFrac = Math.min(pressure / max, 0.99);
        const nc = $8b62e546fdd14731$var$PRESSURE_COLORS[pState] || $8b62e546fdd14731$var$PRESSURE_COLORS.no_contact;
        const { ZONE_BASE: base, ZONE_LOW: low, ZONE_HIGH: high } = $8b62e546fdd14731$var$GAUGE;
        const separators = [
            base,
            low,
            high
        ].map((f)=>{
            const inner = $8b62e546fdd14731$var$fracToXY(f, r - 12);
            const outer = $8b62e546fdd14731$var$fracToXY(f, r + 12);
            return (0, $d33ef1320595a3ac$export$7ed1367e7fa1ad68)`<line x1="${inner.x}" y1="${inner.y}" x2="${outer.x}" y2="${outer.y}" class="zone-separator"/>`;
        });
        const tip = $8b62e546fdd14731$var$fracToXY(needleFrac, r - 16);
        return (0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`
      <div class="gauge-section">
        <svg class="gauge-svg" width="${$8b62e546fdd14731$var$GAUGE_W}" height="186" viewBox="0 0 ${$8b62e546fdd14731$var$GAUGE_W} 186">
          <!-- Track -->
          <path d="${$8b62e546fdd14731$var$describeArc(0, 1)}" fill="none" stroke="var(--ps-track)" stroke-width="${st}" stroke-linecap="butt"/>
          <!-- Zones -->
          <path d="${$8b62e546fdd14731$var$describeArc(0, base)}" fill="none" stroke="var(--ps-track)" stroke-width="${st}" stroke-linecap="round" class="zone-arc"/>
          <path d="${$8b62e546fdd14731$var$describeArc(base, low)}" fill="none" stroke="#42a5f5" stroke-width="${st}" class="zone-arc" opacity="0.5"/>
          <path d="${$8b62e546fdd14731$var$describeArc(low, high)}" fill="none" stroke="#4caf50" stroke-width="${st}" class="zone-arc" opacity="0.65"/>
          <path d="${$8b62e546fdd14731$var$describeArc(high, 1)}" fill="none" stroke="#ff9800" stroke-width="${st}" stroke-linecap="round" class="zone-arc" opacity="0.5"/>
          <!-- Zone separators -->
          ${separators}
          <!-- Session timer -->
          <text x="${cx}" y="${cy - 48}" text-anchor="middle" font-size="10" fill="var(--ps-text-dimmest)" font-family="inherit" letter-spacing="1.5">${this._t("gauge_session")}</text>
          <text x="${cx}" y="${cy - 12}" text-anchor="middle" font-size="38" font-weight="700" fill="var(--primary-text-color, #fff)" font-family="'SF Mono','Menlo','Consolas',monospace" letter-spacing="1">${timerStr}</text>
          <!-- Needle -->
          <line x1="${cx}" y1="${cy + 10}" x2="${tip.x}" y2="${tip.y}" stroke="${nc}" stroke-width="6" class="needle-glow"/>
          <line x1="${cx}" y1="${cy + 10}" x2="${tip.x}" y2="${tip.y}" stroke="${nc}" stroke-width="3" class="needle-line"/>
          <!-- Hub -->
          <circle cx="${cx}" cy="${cy + 10}" r="8" fill="var(--ps-card-bg)" stroke="var(--ps-border)" stroke-width="2"/>
          <circle cx="${cx}" cy="${cy + 10}" r="4" fill="${nc}"/>
          <!-- Edge labels -->
          <text x="26" y="${cy + 28}" class="gauge-edge-label" text-anchor="start">${this._t("gauge_low")}</text>
          <text x="${$8b62e546fdd14731$var$GAUGE_W - 26}" y="${cy + 28}" class="gauge-edge-label" text-anchor="end">${this._t("gauge_high")}</text>
        </svg>
        <div class="pressure-label" style="color:${nc}">${this._t("pressure_" + pState) || "\u2014"}</div>
        <div class="pressure-value">${pressure > 0 ? pressure : "\u2014"}</div>
      </div>
    `;
    }
    _renderSpeedGauge() {
        const { CX: cx, CY: cy, R: r, STROKE: st, SPEED_MAX: max, SPEED_ZONE_OPTIMAL: zoneOpt } = $8b62e546fdd14731$var$GAUGE;
        const speed = this._numState("speed", 0);
        const sState = this._stateVal("speed_verdict", "none");
        const elapsed = this._elapsed || this._numState("shaving_time", 0);
        const tm = Math.floor(elapsed / 60);
        const ts = elapsed % 60;
        const timerStr = String(tm).padStart(2, "0") + ":" + String(ts).padStart(2, "0");
        const needleFrac = Math.min(speed / max, 0.99);
        const nc = $8b62e546fdd14731$var$SPEED_COLORS[sState] || $8b62e546fdd14731$var$SPEED_COLORS.none;
        const separator = (()=>{
            const inner = $8b62e546fdd14731$var$fracToXY(zoneOpt, r - 12);
            const outer = $8b62e546fdd14731$var$fracToXY(zoneOpt, r + 12);
            return (0, $d33ef1320595a3ac$export$7ed1367e7fa1ad68)`<line x1="${inner.x}" y1="${inner.y}" x2="${outer.x}" y2="${outer.y}" class="zone-separator"/>`;
        })();
        const tip = $8b62e546fdd14731$var$fracToXY(needleFrac, r - 16);
        return (0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`
      <div class="gauge-section">
        <svg class="gauge-svg" width="${$8b62e546fdd14731$var$GAUGE_W}" height="186" viewBox="0 0 ${$8b62e546fdd14731$var$GAUGE_W} 186">
          <!-- Track -->
          <path d="${$8b62e546fdd14731$var$describeArc(0, 1)}" fill="none" stroke="var(--ps-track)" stroke-width="${st}" stroke-linecap="butt"/>
          <!-- Zones -->
          <path d="${$8b62e546fdd14731$var$describeArc(0, zoneOpt)}" fill="none" stroke="#4caf50" stroke-width="${st}" stroke-linecap="round" class="zone-arc" opacity="0.65"/>
          <path d="${$8b62e546fdd14731$var$describeArc(zoneOpt, 1)}" fill="none" stroke="#ff9800" stroke-width="${st}" stroke-linecap="round" class="zone-arc" opacity="0.5"/>
          <!-- Zone separator -->
          ${separator}
          <!-- Session timer -->
          <text x="${cx}" y="${cy - 48}" text-anchor="middle" font-size="10" fill="var(--ps-text-dimmest)" font-family="inherit" letter-spacing="1.5">${this._t("gauge_session")}</text>
          <text x="${cx}" y="${cy - 12}" text-anchor="middle" font-size="38" font-weight="700" fill="var(--primary-text-color, #fff)" font-family="'SF Mono','Menlo','Consolas',monospace" letter-spacing="1">${timerStr}</text>
          <!-- Needle -->
          <line x1="${cx}" y1="${cy + 10}" x2="${tip.x}" y2="${tip.y}" stroke="${nc}" stroke-width="6" class="needle-glow"/>
          <line x1="${cx}" y1="${cy + 10}" x2="${tip.x}" y2="${tip.y}" stroke="${nc}" stroke-width="3" class="needle-line"/>
          <!-- Hub -->
          <circle cx="${cx}" cy="${cy + 10}" r="8" fill="var(--ps-card-bg)" stroke="var(--ps-border)" stroke-width="2"/>
          <circle cx="${cx}" cy="${cy + 10}" r="4" fill="${nc}"/>
          <!-- Edge labels -->
          <text x="26" y="${cy + 28}" class="gauge-edge-label" text-anchor="start">${this._t("gauge_slow")}</text>
          <text x="${$8b62e546fdd14731$var$GAUGE_W - 26}" y="${cy + 28}" class="gauge-edge-label" text-anchor="end">${this._t("gauge_fast")}</text>
        </svg>
        <div class="pressure-label" style="color:${nc}">${this._t("speed_" + sState) || "\u2014"}</div>
        <div class="pressure-value">${speed > 0 ? speed : "\u2014"}</div>
      </div>
    `;
    }
    _renderBatteryGauge() {
        const { CX: cx, CY: cy, STROKE: st } = $8b62e546fdd14731$var$GAUGE;
        const bat = this._numState("battery", 0);
        const bc = $8b62e546fdd14731$var$batteryColor(bat);
        return (0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`
      <div class="gauge-section">
        <svg class="gauge-svg" width="${$8b62e546fdd14731$var$GAUGE_W}" height="180" viewBox="0 0 ${$8b62e546fdd14731$var$GAUGE_W} 180">
          <path d="${$8b62e546fdd14731$var$describeArc(0, 1)}" fill="none" stroke="var(--ps-track)" stroke-width="${st}" stroke-linecap="round"/>
          <path d="${$8b62e546fdd14731$var$describeArc(0, bat / 100)}" fill="none" stroke="${bc}" stroke-width="${st}" stroke-linecap="round"/>
          <text x="${cx}" y="${cy - 20}" text-anchor="middle" font-size="52" font-weight="700" fill="var(--primary-text-color, #fff)" font-family="inherit" letter-spacing="-2">${bat}%</text>
          <text x="${cx}" y="${cy + 8}" text-anchor="middle" font-size="13" fill="var(--ps-text-dim)" font-family="inherit">${this._t("gauge_battery")}</text>
        </svg>
        <div class="gauge-status" style="color:var(--ps-text-dimmest)">${this._t("gauge_standby")}</div>
      </div>
    `;
    }
    _renderChargingBattery() {
        const bat = this._numState("battery", 0);
        const fillW = Math.round(bat / 100 * 174);
        const bubbles = [
            {
                size: 3,
                top: 20,
                left: 15,
                dur: 2.5,
                delay: 0
            },
            {
                size: 5,
                top: 45,
                left: 30,
                dur: 3,
                delay: 0.8
            },
            {
                size: 2,
                top: 65,
                left: 50,
                dur: 2.2,
                delay: 1.5
            },
            {
                size: 4,
                top: 35,
                left: 10,
                dur: 3.5,
                delay: 2
            },
            {
                size: 3,
                top: 55,
                left: 40,
                dur: 2.8,
                delay: 0.4
            }
        ];
        return (0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`
      <div class="battery-wrap">
        <div class="battery-container">
          <div class="battery-cap"></div>
          <div class="battery-body">
            <div class="battery-liquid" style="width:${fillW}px">
              <div class="battery-wave-surface">
                <div class="battery-wave-inner">
                  <svg viewBox="0 0 14 200" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg" style="width:14px;height:100%">
                    <path d="M7,0 Q0,12.5 7,25 Q14,37.5 7,50 Q0,62.5 7,75 Q14,87.5 7,100 Q0,112.5 7,125 Q14,137.5 7,150 Q0,162.5 7,175 Q14,187.5 7,200 L14,200 L14,0 Z" fill="#4caf50" opacity="0.75"/>
                  </svg>
                </div>
              </div>
              <div class="battery-bubbles">
                ${bubbles.map((b)=>(0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`
                  <div class="bubble" style="width:${b.size}px;height:${b.size}px;top:${b.top}%;left:${b.left}%;animation-duration:${b.dur}s;animation-delay:${b.delay}s"></div>
                `)}
              </div>
            </div>
            <div class="battery-bolt">
              <svg viewBox="0 0 24 24" fill="#4caf50">
                <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" opacity="0.8"/>
              </svg>
            </div>
          </div>
        </div>
        <div class="battery-pct">${bat}%</div>
        <div class="battery-sub">
          <span class="charge-dot"></span>
          <span class="charge-dot"></span>
          <span class="charge-dot"></span>
          <span style="margin-left:2px">${this._t("gauge_charging")}</span>
        </div>
      </div>
    `;
    }
    _renderCleaningGauge() {
        const progress = this._numState("cleaning_progress", 0);
        const frac = Math.max(0, Math.min(1, progress / 100));
        const cx = 80, cy = 80, r = 66, sw = 10;
        const START = 135, range = 270;
        const cleanRingArc = (f)=>{
            const startRad = START * Math.PI / 180;
            const endRad = (START + range * f) * Math.PI / 180;
            const x1 = cx + r * Math.cos(startRad), y1 = cy + r * Math.sin(startRad);
            const x2 = cx + r * Math.cos(endRad), y2 = cy + r * Math.sin(endRad);
            const large = range * f > 180 ? 1 : 0;
            return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
        };
        const droplets = [
            {
                size: 6,
                angle: 160,
                dur: 2,
                delay: 0
            },
            {
                size: 8,
                angle: 220,
                dur: 2.5,
                delay: 0.5
            },
            {
                size: 5,
                angle: 300,
                dur: 1.8,
                delay: 1.2
            },
            {
                size: 7,
                angle: 370,
                dur: 2.2,
                delay: 1.8
            },
            {
                size: 6,
                angle: 250,
                dur: 2.8,
                delay: 0.8
            }
        ];
        return (0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`
      <div class="cleaning-wrap">
        <div class="cleaning-gauge-ring">
          <svg class="cleaning-ring-svg" viewBox="0 0 160 160">
            <path d="${cleanRingArc(1)}" fill="none" stroke="var(--ps-track)" stroke-width="${sw}" stroke-linecap="round"/>
            <path d="${cleanRingArc(frac)}" fill="none" stroke="#42a5f5" stroke-width="${sw}" stroke-linecap="round" class="cleaning-arc-fill"/>
          </svg>
          <div class="cleaning-center">
            <div class="cleaning-pct">${Math.round(progress)}%</div>
            <div class="cleaning-label">${this._t("gauge_cleaning")}</div>
          </div>
          <div class="cleaning-droplets">
            ${droplets.map((d)=>{
            const rad = d.angle * Math.PI / 180;
            const dx = cx + (r + 16) * Math.cos(rad);
            const dy = cy + (r + 16) * Math.sin(rad);
            return (0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`<div class="droplet" style="width:${d.size}px;height:${d.size}px;left:${dx - d.size / 2}px;top:${dy - d.size / 2}px;animation-duration:${d.dur}s;animation-delay:${d.delay}s"></div>`;
        })}
          </div>
        </div>
        <div class="cleaning-status">
          <div class="clean-spinner"></div>
          ${this._t("gauge_in_progress")}
        </div>
      </div>
    `;
    }
    // ---------- Stats ----------
    _renderStats(activity) {
        if (activity === "shaving") return this._renderShaveStats();
        let rows;
        if (activity === "charging") rows = (0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`
        ${this._statRow("charges", this._t("stat_charge_cycles"), this._numState("amount_of_charges", 0))}
        ${this._statRow("clock", this._t("stat_last_session"), $8b62e546fdd14731$var$formatSession(this._numState("shaving_time", 0)))}
        ${this._statRow("counter", this._t("stat_total_uses"), this._numState("amount_of_operational_turns", 0))}
        ${this._statRow("clock", this._t("stat_total_time"), $8b62e546fdd14731$var$formatAge(this._numState("total_age", 0)))}
      `;
        else if (activity === "cleaning") {
            const remaining = this._numState("cleaning_cycles_remaining", 0);
            rows = (0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`
        ${this._statRow("droplet", this._t("stat_cycles_remaining"), remaining.toFixed(1))}
        ${this._statRow("clock", this._t("stat_last_session"), $8b62e546fdd14731$var$formatSession(this._numState("shaving_time", 0)))}
        ${this._statRow("counter", this._t("stat_total_uses"), this._numState("amount_of_operational_turns", 0))}
      `;
        } else {
            const daysUsed = this._numState("days_last_used", null);
            let daysText;
            if (daysUsed === null) daysText = "\u2014";
            else if (daysUsed === 0) daysText = this._t("time_today");
            else if (daysUsed === 1) daysText = this._t("time_yesterday");
            else daysText = this._t("time_days_ago").replace("{n}", daysUsed);
            rows = (0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`
        ${this._statRow("clock", this._t("stat_last_session"), $8b62e546fdd14731$var$formatSession(this._numState("shaving_time", 0)))}
        ${this._statRow("calendar", this._t("stat_last_used"), daysText)}
        ${this._statRow("clock", this._t("stat_total_time"), $8b62e546fdd14731$var$formatAge(this._numState("total_age", 0)))}
        ${this._statRow("counter", this._t("stat_total_uses"), this._numState("amount_of_operational_turns", 0))}
      `;
        }
        return (0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`<div class="stats">${rows}</div>`;
    }
    _renderShaveStats() {
        const rpm = this._numState("motor_rpm", 0);
        const ma = this._numState("motor_current", 0);
        if (this._isOneBlade) return (0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`
        <div class="shave-stats">
          <div class="shave-stat-tile">
            <div class="shave-stat-val">${ma}</div>
            <div class="shave-stat-label">${this._t("shave_ma")}</div>
          </div>
          <div class="shave-stat-tile">
            <div class="shave-stat-val">${this._numState("speed", 0)}</div>
            <div class="shave-stat-label">${this._t("shave_speed")}</div>
          </div>
        </div>
      `;
        const motion = this._stateVal("motion_type", "no_motion");
        const motionText = motion === "no_motion" ? "\u2014" : this._t("motion_" + motion);
        return (0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`
      <div class="shave-stats">
        <div class="shave-stat-tile">
          <div class="shave-stat-val">${rpm}</div>
          <div class="shave-stat-label">${this._t("shave_rpm")}</div>
        </div>
        <div class="shave-stat-tile">
          <div class="shave-stat-val">${ma}</div>
          <div class="shave-stat-label">${this._t("shave_ma")}</div>
        </div>
        <div class="shave-stat-tile">
          <div class="shave-stat-val">${motionText}</div>
          <div class="shave-stat-label">${this._t("shave_motion")}</div>
        </div>
      </div>
    `;
    }
    _statRow(icon, label, value, unit) {
        return (0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`
      <div class="stat-row">
        <span class="stat-label">
          <svg class="stat-icon" viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <path d="${$8b62e546fdd14731$var$ICONS[icon] || ''}"/>
          </svg>
          ${label}
        </span>
        <span class="stat-value">${value}${unit ? (0, $d33ef1320595a3ac$export$c0bb0b647f701bb5)`<span class="stat-unit">${unit}</span>` : ''}</span>
      </div>
    `;
    }
    // ---------- Styles ----------
    static get styles() {
        return (0, $06bdd16cbb4a41b3$export$8d80f9cac07cdb3)((0, (/*@__PURE__*/$parcel$interopDefault($43a89528e95f706e$exports))));
    }
    // ---------- Config form ----------
    static getConfigForm() {
        return {
            schema: [
                {
                    name: "title",
                    label: (0, $d8078e452c66bdbe$export$625550452a3fa3ec)(null, "config_title"),
                    selector: {
                        text: {}
                    }
                },
                {
                    name: "show_model",
                    label: (0, $d8078e452c66bdbe$export$625550452a3fa3ec)(null, "config_show_model"),
                    selector: {
                        boolean: {}
                    },
                    default: true
                },
                {
                    name: "device_id",
                    required: true,
                    selector: {
                        device: {
                            filter: [
                                {
                                    integration: "philips_shaver"
                                }
                            ],
                            entity: [
                                {
                                    domain: "sensor",
                                    device_class: "battery"
                                }
                            ],
                            multiple: false
                        }
                    }
                }
            ]
        };
    }
    static getStubConfig(hass) {
        const entry = Object.values(hass.entities).find((e)=>e.platform === "philips_shaver" && e.translation_key === "battery");
        return {
            device_id: entry ? entry.device_id : ""
        };
    }
}




const $5b8472df96c6a1cc$var$TAG = "philips-shaver-card";
const $5b8472df96c6a1cc$var$BANNER_ID = "philips-shaver-card-outdated-banner";
// Custom elements can only be defined once, so when two copies of the card are
// loaded (bundled with the integration + leftover standalone install) the first
// one wins. If an outdated copy won, this bundled copy patches the winner so
// every rendered card shows a visible hint on top of the console warning and
// the integration's repair issue.
function $5b8472df96c6a1cc$var$markOutdatedCards(WinnerClass) {
    const inject = (card)=>{
        const root = card.renderRoot ?? card.shadowRoot;
        if (!root || root.querySelector(`#${$5b8472df96c6a1cc$var$BANNER_ID}`)) return;
        const haCard = root.querySelector("ha-card");
        if (!haCard) return; // not rendered yet — retry on the next update
        const banner = document.createElement("div");
        banner.id = $5b8472df96c6a1cc$var$BANNER_ID;
        banner.style.cssText = "background:var(--warning-color,#ffa600);color:var(--text-primary-color,#fff);padding:6px 12px;font-size:12px;line-height:1.3;font-weight:500;border-radius:var(--ha-card-border-radius,12px) var(--ha-card-border-radius,12px) 0 0;";
        banner.textContent = `\u{26A0}\u{FE0F} ${(0, $d8078e452c66bdbe$export$625550452a3fa3ec)(card.hass ?? card._hass, "outdated_standalone_active")}`;
        haCard.prepend(banner);
    };
    const origUpdated = WinnerClass.prototype.updated;
    WinnerClass.prototype.updated = function(...args) {
        origUpdated?.apply(this, args);
        try {
            inject(this);
        } catch (e) {
        // Never break the (old) card over a hint.
        }
    };
}
const $5b8472df96c6a1cc$var$winner = customElements.get($5b8472df96c6a1cc$var$TAG);
if ($5b8472df96c6a1cc$var$winner) {
    console.warn(`philips-shaver-card v${(0, $8ee5ce714273e53b$export$d5e7ce6d07daf10f)} [${(0, $8ee5ce714273e53b$export$9b657414b7dffe40)}] was not loaded: ` + "another copy of the card is already registered. The card ships with the " + "Philips Shaver integration \u2014 if the standalone card is still installed " + "(HACS or manual resource), remove it to avoid running an outdated version.");
    if ((0, $8ee5ce714273e53b$export$9b657414b7dffe40) === "bundled" && $5b8472df96c6a1cc$var$winner.CARD_ORIGIN !== "bundled") $5b8472df96c6a1cc$var$markOutdatedCards($5b8472df96c6a1cc$var$winner);
} else {
    // Marker for other copies to recognize which variant won the race.
    (0, $8b62e546fdd14731$export$4778d74453ecc150).CARD_VERSION = (0, $8ee5ce714273e53b$export$d5e7ce6d07daf10f);
    (0, $8b62e546fdd14731$export$4778d74453ecc150).CARD_ORIGIN = (0, $8ee5ce714273e53b$export$9b657414b7dffe40);
    customElements.define($5b8472df96c6a1cc$var$TAG, (0, $8b62e546fdd14731$export$4778d74453ecc150));
    window.customCards = window.customCards || [];
    window.customCards.push({
        type: $5b8472df96c6a1cc$var$TAG,
        name: "Philips Shaver Card",
        description: "Custom card for the Philips Shaver integration with pressure gauge, battery, and diagnostics.",
        preview: true,
        // Card picker suggestion (HA 2026.6+): suggest this card for any
        // philips_shaver entity. The picked entity may sit on a sub-device
        // (e.g. Connection), so normalize to the device owning the battery
        // entity within the same config entry — same shape as getStubConfig.
        getEntitySuggestion: (hass, entityId)=>{
            const entity = hass.entities?.[entityId];
            if (!entity || entity.platform !== "philips_shaver") return null;
            const devices = hass.devices || {};
            const entryIds = devices[entity.device_id]?.config_entries || [];
            const main = Object.values(hass.entities).find((e)=>e.platform === "philips_shaver" && e.translation_key === "battery" && (e.device_id === entity.device_id || (devices[e.device_id]?.config_entries || []).some((ce)=>entryIds.includes(ce))));
            const deviceId = (main ?? entity).device_id;
            // setConfig rejects a falsy device_id — better no suggestion than
            // one whose preview renders an error card.
            return deviceId ? {
                config: {
                    type: `custom:${$5b8472df96c6a1cc$var$TAG}`,
                    device_id: deviceId
                }
            } : null;
        }
    });
    console.info(`%c PHILIPS-SHAVER-CARD %c v${(0, $8ee5ce714273e53b$export$d5e7ce6d07daf10f)} [${(0, $8ee5ce714273e53b$export$9b657414b7dffe40)}] `, "color:#fff;background:#1c1c1c;padding:2px 6px;border-radius:4px 0 0 4px;font-weight:700", "color:#1c1c1c;background:#ffab40;padding:2px 6px;border-radius:0 4px 4px 0;font-weight:700");
}


