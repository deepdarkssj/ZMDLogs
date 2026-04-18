(function () {
  const query = new URLSearchParams(window.location.search);
  const wsPort = query.get("wsPort") || "29325";
  const wsUrl = `ws://127.0.0.1:${wsPort}/ws`;

  const state = {
    sessionId: null,
    squad: new Map(),
    players: new Map(),
    totalDamage: 0,
    startTime: 0,
    currentTime: Date.now(),
    isCombatActive: false,
    lastDamageAt: 0,
  };

  const refs = {
    totalDamage: document.getElementById("totalDamage"),
    totalDps: document.getElementById("totalDps"),
    combatTime: document.getElementById("combatTime"),
    combatIndicator: document.getElementById("combatIndicator"),
    rows: document.getElementById("rows"),
    emptyState: document.getElementById("emptyState"),
    footer: document.getElementById("footer"),
    footerText: document.getElementById("footerText"),
  };

  let ws = null;
  let reconnectTimer = null;

  function resetState(nextSessionId) {
    state.sessionId = nextSessionId || null;
    state.squad.clear();
    state.players.clear();
    state.totalDamage = 0;
    state.startTime = 0;
    state.currentTime = Date.now();
    state.isCombatActive = false;
    state.lastDamageAt = 0;
    render();
  }

  function ensureSession(sessionId) {
    if (!sessionId) {
      return;
    }
    if (state.sessionId === null) {
      resetState(sessionId);
      return;
    }
    if (state.sessionId !== sessionId) {
      resetState(sessionId);
    }
  }

  function ensurePlayer(id, displayName, squadIndex) {
    const key = String(id);
    const existing = state.players.get(key);
    if (existing) {
      if (displayName && existing.name !== displayName) {
        existing.name = displayName;
      }
      if (typeof squadIndex === "number") {
        existing.squadIndex = squadIndex;
      }
      return existing;
    }

    const created = {
      id: key,
      name: displayName || `#${key}`,
      totalDamage: 0,
      maxDamage: 0,
      critCount: 0,
      hitCount: 0,
      lastUpdate: Date.now(),
      squadIndex: typeof squadIndex === "number" ? squadIndex : Number.MAX_SAFE_INTEGER,
    };
    state.players.set(key, created);
    return created;
  }

  function applySquadUpdate(event) {
    ensureSession(event.session_id);
    state.squad.clear();
    for (const member of event.members || []) {
      const key = String(member.battle_inst_id);
      state.squad.set(key, member);
      ensurePlayer(member.battle_inst_id, member.display_name || `#${key}`, member.squad_index);
    }
    render();
  }

  function applyDamage(event) {
    ensureSession(event.session_id);
    const attacker = event.attacker || {};
    const attackerId = attacker.battle_inst_id;
    if (!attackerId) {
      return;
    }

    const key = String(attackerId);
    const squadMember = state.squad.get(key);
    const displayName = (squadMember && squadMember.display_name) || attacker.display_name || `#${key}`;
    const player = ensurePlayer(attackerId, displayName, squadMember ? squadMember.squad_index : undefined);

    const totalEventDamage = (event.details || []).reduce((sum, detail) => {
      if (typeof detail.abs_value === "number") {
        return sum + detail.abs_value;
      }
      if (typeof detail.value === "number") {
        return sum + Math.abs(detail.value);
      }
      return sum;
    }, 0);

    if (!totalEventDamage) {
      return;
    }

    const isCrit = (event.details || []).some((detail) => Boolean(detail.is_crit));
    player.name = displayName;
    player.totalDamage += totalEventDamage;
    player.maxDamage = Math.max(player.maxDamage, totalEventDamage);
    player.critCount += isCrit ? 1 : 0;
    player.hitCount += 1;
    player.lastUpdate = Date.now();
    state.totalDamage += totalEventDamage;
    state.currentTime = Date.now();
    state.lastDamageAt = state.currentTime;
    state.isCombatActive = true;
    if (!state.startTime) {
      state.startTime = event.timestamp_ms || state.currentTime;
    }
    render();
  }

  function handleHello(payload) {
    ensureSession(payload.session_id || null);
  }

  function handlePayload(payload) {
    if (!payload || typeof payload !== "object") {
      return;
    }

    if (payload.type === "hello") {
      handleHello(payload);
      return;
    }

    if (payload.type === "event_batch") {
      for (const event of payload.events || []) {
        handlePayload(event);
      }
      return;
    }

    if (payload.type === "squad_update") {
      applySquadUpdate(payload);
      return;
    }

    if (payload.type === "damage") {
      applyDamage(payload);
    }
  }

  function formatNumber(value, maximumFractionDigits) {
    return value.toLocaleString(undefined, { maximumFractionDigits });
  }

  function formatTime(ms) {
    const totalSeconds = Math.max(0, Math.floor(ms / 1000));
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    return [
      String(hours).padStart(2, "0"),
      String(minutes).padStart(2, "0"),
      String(seconds).padStart(2, "0"),
    ].join(":");
  }

  function initialsFor(name) {
    const normalized = String(name || "?").trim();
    if (!normalized) {
      return "?";
    }
    const plain = normalized.replace(/\s+/g, "");
    return plain.slice(0, 2).toUpperCase();
  }

  function renderRows(players) {
    refs.rows.innerHTML = "";
    if (!players.length) {
      refs.emptyState.classList.remove("hidden");
      return;
    }

    refs.emptyState.classList.add("hidden");
    const totalDamage = state.totalDamage || 1;
    for (const [index, player] of players.entries()) {
      const damagePercent = Math.max(0, Math.min(100, (player.totalDamage / totalDamage) * 100));
      const critRate = player.hitCount ? (player.critCount / player.hitCount) * 100 : 0;
      const row = document.createElement("div");
      row.className = "row";
      row.innerHTML = `
        <div class="row-progress" style="width:${damagePercent}%"></div>
        <div class="row-accent ${index % 2 === 0 ? "primary" : "dark"}"></div>
        <div class="row-avatar">
          <div class="avatar-initials">${initialsFor(player.name)}</div>
          <div class="avatar-slot">C_${String(index + 1).padStart(2, "0")}</div>
        </div>
        <div class="row-name">
          <div class="player-name">${player.name}</div>
          <div class="player-meta">MAX_DMG: ${formatNumber(player.maxDamage, 0)}</div>
        </div>
        <div class="row-damage">${formatNumber(player.totalDamage, 0)}</div>
        <div class="row-crit">${critRate.toFixed(1)}%</div>
      `;
      refs.rows.appendChild(row);
    }
  }

  function render() {
    const now = Date.now();
    state.currentTime = now;
    if (state.isCombatActive && state.lastDamageAt && now - state.lastDamageAt > 8000) {
      state.isCombatActive = false;
    }

    const elapsed = state.startTime ? Math.max(1, (now - state.startTime) / 1000) : 1;
    const totalDps = state.totalDamage / elapsed;
    refs.totalDamage.textContent = formatNumber(state.totalDamage, 0);
    refs.totalDps.textContent = formatNumber(totalDps, 1);
    refs.combatTime.textContent = formatTime(state.startTime ? now - state.startTime : 0);
    refs.combatIndicator.classList.toggle("active", state.isCombatActive);
    refs.footer.classList.toggle("active", state.isCombatActive);
    refs.footerText.textContent = state.isCombatActive ? "IN_COMBAT // 战斗中" : "STANDBY // 待机中";

    const players = Array.from(state.players.values()).sort((a, b) => {
      if (b.totalDamage !== a.totalDamage) {
        return b.totalDamage - a.totalDamage;
      }
      if (a.squadIndex !== b.squadIndex) {
        return a.squadIndex - b.squadIndex;
      }
      return a.id.localeCompare(b.id);
    });
    renderRows(players);
  }

  function scheduleReconnect() {
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer);
    }
    reconnectTimer = window.setTimeout(connect, 1500);
  }

  function connect() {
    if (ws) {
      ws.close();
    }
    ws = new WebSocket(wsUrl);
    ws.onmessage = (message) => {
      try {
        handlePayload(JSON.parse(message.data));
      } catch (error) {
        console.error("overlay ws parse error", error);
      }
    };
    ws.onclose = () => {
      scheduleReconnect();
    };
    ws.onerror = () => {
      if (ws) {
        ws.close();
      }
    };
  }

  window.setInterval(render, 1000);
  resetState(null);
  connect();
})();
