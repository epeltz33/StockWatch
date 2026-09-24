/*
 * Browser-side callbacks for the StockWatch dashboard (see dashboard.py).
 *
 * These run without a server round trip: section switching, the active
 * watchlist ticker, saving and reading selections in sessionStorage, and a
 * few small toggles. Nothing here touches market or account data.
 */
(function () {
    "use strict";

    var noUpdate = function () {
        return window.dash_clientside.no_update;
    };

    function triggered() {
        var ctx = window.dash_clientside.callback_context;
        if (!ctx || !ctx.triggered || !ctx.triggered.length) {
            return {id: null, value: null};
        }
        var first = ctx.triggered[0];
        var rawId = first.prop_id.slice(0, first.prop_id.lastIndexOf("."));
        var id = rawId;
        if (rawId.charAt(0) === "{") {
            try {
                id = JSON.parse(rawId);
            } catch (e) {
                id = rawId;
            }
        }
        return {id: id, value: first.value};
    }

    function focusWhenVisible(id, timeoutMs) {
        var started = Date.now();
        (function attempt() {
            var el = document.getElementById(id);
            if (el && el.offsetParent !== null) {
                el.focus();
                return;
            }
            if (Date.now() - started < timeoutMs) {
                window.setTimeout(attempt, 30);
            }
        })();
    }

    function readStorage(key) {
        try {
            var raw = window.sessionStorage.getItem(key);
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            // Private mode or blocked storage: behave as if nothing was saved
            return null;
        }
    }

    function writeStorage(key, value) {
        try {
            window.sessionStorage.setItem(key, JSON.stringify(value));
        } catch (e) {
            /* storage unavailable: selections just aren't kept */
        }
    }

    window.dash_clientside = Object.assign({}, window.dash_clientside, {
        stockwatch: {
            /* Selections saved earlier in this browser session, or {} — the
             * server validates anything it gets here (watchlist ownership,
             * symbol format), since sessionStorage is client-controlled. */
            readSavedState: function (boot) {
                if (!boot || !boot.storage_key) {
                    return {};
                }
                var saved = readStorage(boot.storage_key);
                if (!saved || saved.user !== boot.user) {
                    return {};
                }
                return {
                    symbol: typeof saved.symbol === "string" ? saved.symbol : null,
                    period: typeof saved.period === "string" ? saved.period : null,
                    watchlist_id: saved.watchlist_id === undefined ? null : saved.watchlist_id
                };
            },

            saveState: function (symbol, period, watchlistId, boot) {
                var state = {
                    user: boot ? boot.user : null,
                    symbol: symbol || null,
                    period: period || null,
                    watchlist_id: watchlistId === undefined ? null : watchlistId
                };
                if (boot && boot.storage_key) {
                    writeStorage(boot.storage_key, state);
                }
                return state;
            },

            /* Turn a real click on a ticker button into a load request.
             * Buttons being rendered fire with zero clicks; those return
             * no_update so they never re-trigger (and cancel) the loader. */
            requestSymbol: function (_chips, _rows, _retry, failedSymbol) {
                var t = triggered();
                if (!t.value || !t.id || typeof t.id !== "object") {
                    return noUpdate();
                }
                var retry = t.id.type === "retry-search";
                var symbol = retry ? failedSymbol : t.id.index;
                if (!symbol) {
                    return noUpdate();
                }
                return {symbol: symbol, origin: retry ? "retry" : "click", at: Date.now()};
            },

            /* Generic gate for buttons rendered by callbacks: a real click
             * becomes {type, index, at}; the zero-click fire on render
             * becomes no_update. */
            clickRequest: function () {
                var t = triggered();
                if (!t.value || !t.id || typeof t.id !== "object") {
                    return noUpdate();
                }
                return {type: t.id.type, index: t.id.index, at: Date.now()};
            },

            markActiveTicker: function (symbol, _rows, ids) {
                var classes = ids.map(function (id) {
                    return id.index === symbol
                        ? "watchlist-select watchlist-select--active"
                        : "watchlist-select";
                });
                var current = ids.map(function (id) {
                    return id.index === symbol ? "true" : "false";
                });
                return [classes, current];
            },

            selectSection: function () {
                var t = triggered();
                if (!t.value || !t.id || typeof t.id !== "object") {
                    return noUpdate();
                }
                return t.id.index;
            },

            showSection: function (section, ids) {
                var classes = ids.map(function (id) {
                    return id.index === section ? "sw-nav-btn sw-nav-btn--active" : "sw-nav-btn";
                });
                var current = ids.map(function (id) {
                    return id.index === section ? "page" : "false";
                });
                // Plotly sizes graphs when drawn; ones drawn while their
                // section was hidden need a resize once it is shown.
                window.setTimeout(function () {
                    window.dispatchEvent(new Event("resize"));
                }, 0);
                return [classes, current, section !== "market", section !== "portfolio"];
            },

            /* Refresh prices only while the Market section is on screen. */
            pollWhileVisible: function (section) {
                return section !== "market";
            },

            toggleCreateForm: function (toggleClicks, cancelClicks, openClicks, isOpen) {
                var t = triggered();
                if (!t.value) {
                    return [noUpdate(), noUpdate()];
                }
                var open;
                if (t.id === "new-watchlist-cancel") {
                    open = false;
                } else if (typeof t.id === "object") {
                    open = true;
                } else {
                    open = !isOpen;
                }
                if (open) {
                    // The collapse renders a moment after this returns; move
                    // focus into the name field as soon as it's visible.
                    focusWhenVisible("new-watchlist-input", 1500);
                } else {
                    var toggle = document.getElementById("new-watchlist-toggle");
                    if (toggle && t.id === "new-watchlist-cancel") {
                        toggle.focus();
                    }
                }
                return [open, open ? "true" : "false"];
            },

            cancelConfirm: function (clicks) {
                if (!clicks) {
                    return [noUpdate(), noUpdate()];
                }
                return [false, null];
            }
        }
    });
})();
