const updateInterval = 1000; // Poll every second

// ===== Brain Selector =====
let brainsLoaded = false;

async function loadBrains() {
    try {
        const res = await fetch('/api/brains');
        if (!res.ok) return;
        const brains = await res.json();
        
        const select = document.getElementById('brain-select');
        // Clear existing options except the placeholder
        select.innerHTML = '<option value="" disabled>Switch Brain...</option>';
        
        for (const [id, info] of Object.entries(brains)) {
            const opt = document.createElement('option');
            opt.value = id;
            opt.textContent = info.name;
            if (info.active) opt.selected = true;
            select.appendChild(opt);
        }
        
        brainsLoaded = true;
    } catch (e) {
        console.error("Error loading brains:", e);
    }
}

document.getElementById('brain-select').addEventListener('change', async (e) => {
    const brainId = e.target.value;
    if (!brainId) return;
    
    const confirmed = window.confirm(
        `Switch ADA's brain to "${e.target.options[e.target.selectedIndex].text}"?\n\n` +
        `This will change her trading strategy, risk profile, and tick speed.`
    );
    if (!confirmed) {
        // Revert selection
        await loadBrains();
        return;
    }
    
    try {
        const res = await fetch('/api/switch_brain', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ brain_id: brainId }),
        });
        const data = await res.json();
        if (data.status === 'success') {
            await loadBrains();
            await fetchState();
        } else {
            alert(`Failed to switch brain: ${data.message}`);
            await loadBrains();
        }
    } catch (e) {
        console.error("Error switching brain:", e);
        await loadBrains();
    }
});

// ===== State Polling =====
async function fetchState() {
    try {
        const response = await fetch('/api/state');
        if (!response.ok) throw new Error('Network response was not ok');
        const state = await response.json();
        updateUI(state);
    } catch (error) {
        console.error("Error fetching state:", error);
        document.getElementById('status-text').innerText = "Disconnected";
        document.getElementById('status-ring').className = "pulse-ring error";
    }
}

function updateUI(state) {
    // Header Status
    const statusText = document.getElementById('status-text');
    const statusRing = document.getElementById('status-ring');
    statusText.innerText = state.status;
    if (state.status === "Running") {
        statusRing.className = "pulse-ring active";
    } else {
        statusRing.className = "pulse-ring error";
    }
    
    // Formatting numbers
    const formatCurrency = (num) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(num);

    if (state.balance) {
        document.getElementById('testnet-balance').innerText = `Testnet Pool: ${formatCurrency(state.balance)}`;
    }

    // Brain Info
    document.getElementById('brain-text').innerText = state.brain;
    
    // Brain Profile Info
    if (state.brain_profile) {
        const bp = state.brain_profile;
        document.getElementById('brain-profile-info').innerHTML = 
            `⏱ ${bp.tick_interval}s tick · ` +
            `🛡 SL: ${(bp.stop_loss_pct * 100).toFixed(2)}% · ` +
            `🎯 TP: ${(bp.take_profit_pct * 100).toFixed(2)}%` +
            (bp.max_hold_candles ? ` · ⏳ Max: ${bp.max_hold_candles} candles` : '');
    }

    // Grid Stats
    document.getElementById('symbol-text').innerText = state.symbol;
    document.getElementById('price-text').innerText = formatCurrency(state.current_price);
    
    // Thesis Engine Rendering
    if (state.thesis) {
        document.getElementById('working-capital').innerText = formatCurrency(state.thesis.working_capital);
        document.getElementById('initial-capital').innerText = formatCurrency(state.thesis.initial_capital);
        document.getElementById('claimable-vault').innerText = formatCurrency(state.thesis.claimable_vault);
        document.getElementById('win-rate').innerText = `Win Rate: ${state.thesis.win_rate.toFixed(1)}%`;
        document.getElementById('total-trades').innerText = `Trades: ${state.thesis.total_trades}`;
        
        // Show deployed capital sub-label only when position is open
        const deployedLabel = document.getElementById('deployed-capital-label');
        if (state.position !== 'None' && state.position_size > 0) {
            document.getElementById('deployed-capital').innerText = formatCurrency(state.position_size);
            deployedLabel.style.display = 'block';
            deployedLabel.style.color = '#ffaa00';
        } else {
            deployedLabel.style.display = 'none';
        }
        
        document.getElementById('target-text').innerText = `${formatCurrency(state.thesis.claimable_vault)} / ${formatCurrency(state.thesis.daily_target)}`;
        document.getElementById('progress-bar-fill').style.width = `${Math.min(state.thesis.target_progress_pct, 100)}%`;
    }
    
    // === Dynamic Brain Metrics ===
    const metricsPanel = document.getElementById('metrics-panel');
    if (state.metrics) {
        // Build metrics dynamically — each brain can return different keys
        const skipKeys = ['Internal Monologue', 'predicted_prices', 'Status'];
        const metricEntries = Object.entries(state.metrics).filter(([k]) => !skipKeys.includes(k));
        
        // Only rebuild DOM if metric keys changed
        const currentKeys = metricEntries.map(([k]) => k).join(',');
        if (metricsPanel.dataset.keys !== currentKeys) {
            metricsPanel.innerHTML = '';
            for (const [key, value] of metricEntries) {
                const row = document.createElement('div');
                row.className = 'metric-row';
                row.innerHTML = `
                    <span class="metric-label">${key}</span>
                    <span class="metric-value" data-metric-key="${key}">${value}</span>
                `;
                metricsPanel.appendChild(row);
            }
            metricsPanel.dataset.keys = currentKeys;
        } else {
            // Just update values without rebuilding DOM
            for (const [key, value] of metricEntries) {
                const el = metricsPanel.querySelector(`[data-metric-key="${key}"]`);
                if (el) el.innerText = value;
            }
        }
        
        document.getElementById('metric-thought').innerText = state.metrics["Internal Monologue"] || state.metrics["Status"] || "Thinking...";
    } else {
        metricsPanel.innerHTML = '<span class="metric-label">Waiting for data...</span>';
        document.getElementById('metric-thought').innerText = "Warming up indicators...";
    }
    
    // === Trade Stats ===
    if (state.trade_stats) {
        document.getElementById('stat-trades').innerText = `Trades: ${state.trade_stats.total_trades}`;
        document.getElementById('stat-winrate').innerText = `WR: ${state.trade_stats.win_rate.toFixed(0)}%`;
        document.getElementById('stat-avghold').innerText = `Avg Hold: ${state.trade_stats.avg_hold_seconds.toFixed(0)}s`;
    }

    // Action Badge
    const actionBadge = document.getElementById('action-badge');
    actionBadge.innerText = state.latest_action;
    actionBadge.className = `badge ${state.latest_action.toLowerCase().replace('_', ' ')}`;

    // Position Details
    const positionType = document.getElementById('position-type');
    positionType.innerText = state.position;
    if (state.position === "LONG") {
        positionType.className = "badge buy";
    } else {
        positionType.className = "badge neutral";
    }

    document.getElementById('entry-price').innerText = state.entry_price > 0 ? formatCurrency(state.entry_price) : "--";
    
    const plSpan = document.getElementById('profit-loss');
    const plUsdSpan = document.getElementById('profit-loss-usd');
    const sizeSpan = document.getElementById('position-size');
    
    if (state.position === "None") {
        plSpan.innerText = "--";
        plSpan.className = "neutral";
        sizeSpan.innerText = "--";
        plUsdSpan.innerText = "--";
        plUsdSpan.className = "neutral";
    } else {
        const pl = state.profit_loss_pct;
        plSpan.innerText = `${pl > 0 ? '+' : ''}${pl.toFixed(4)}%`;
        plSpan.className = pl >= 0 ? "profit" : "loss";
        
        sizeSpan.innerText = formatCurrency(state.position_size || 0);
        
        const plUsd = state.profit_loss_usd || 0;
        plUsdSpan.innerText = `${plUsd > 0 ? '+' : ''}${formatCurrency(Math.abs(plUsd))}`;
        plUsdSpan.className = plUsd >= 0 ? "profit" : "loss";
    }
}

// --- Charting Engine ---
let chart;
let candlestickSeries;
let forecastSeries;

async function initChart() {
    const container = document.getElementById('chart-container');
    chart = LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height: 400,
        layout: {
            backgroundColor: 'transparent',
            textColor: '#8e8e99',
        },
        grid: {
            vertLines: { visible: false },
            horzLines: { color: 'rgba(255, 255, 255, 0.08)' },
        },
        timeScale: {
            timeVisible: true,
            secondsVisible: false,
        },
    });

    candlestickSeries = chart.addCandlestickSeries({
        upColor: '#00f0ff', // Cyan
        downColor: '#7000ff', // Purple
        borderVisible: false,
        wickUpColor: '#00f0ff',
        wickDownColor: '#7000ff',
    });

    forecastSeries = chart.addLineSeries({
        color: '#ffaa00', // Orange/Gold
        lineWidth: 2,
        lineStyle: 2, // Dashed line
    });

    await updateChartData();
    setInterval(updateChartData, 5000); // Refresh chart every 5s
}

async function updateChartData() {
    try {
        const [chartRes, tradeRes, stateRes] = await Promise.all([
            fetch('/api/chart_data'),
            fetch('/api/trade_history'),
            fetch('/api/state')
        ]);
        
        let validTimes = new Set();
        
        if (chartRes.ok) {
            let data = await chartRes.json();
            
            // Ensure data is strictly increasing to prevent setData crashes
            const uniqueData = [];
            let lastTime = 0;
            for (const row of data) {
                if (row.time > lastTime) {
                    uniqueData.push(row);
                    validTimes.add(row.time);
                    lastTime = row.time;
                }
            }
            candlestickSeries.setData(uniqueData);

            if (stateRes.ok) {
                const state = await stateRes.json();
                if (state.metrics && state.metrics.predicted_prices && uniqueData.length > 0) {
                    const forecastData = [];
                    let fTime = lastTime; 
                    
                    forecastData.push({ time: fTime, value: uniqueData[uniqueData.length - 1].close });
                    
                    for (let i = 0; i < state.metrics.predicted_prices.length; i++) {
                        fTime += 60;
                        forecastData.push({
                            time: fTime,
                            value: state.metrics.predicted_prices[i]
                        });
                    }
                    forecastSeries.setData(forecastData);
                } else {
                    // Clear forecast line if the current brain doesn't use it
                    forecastSeries.setData([]);
                }
            }
        }
        
        if (tradeRes.ok) {
            const trades = await tradeRes.json();
            const markers = [];
            
            for (const trade of trades) {
                // Round down to the nearest 1m candle (60 seconds)
                let candleTime = Math.floor(trade.time / 60) * 60;
                
                // Only add the marker if the candle time exists in the chart data
                if (validTimes.has(candleTime)) {
                    markers.push({
                        time: candleTime,
                        position: trade.side === 'BUY' ? 'belowBar' : 'aboveBar',
                        color: trade.side === 'BUY' ? '#00ff88' : '#ff3366',
                        shape: trade.side === 'BUY' ? 'arrowUp' : 'arrowDown',
                        text: trade.side === 'BUY' ? 'Buy' : 'Sell',
                    });
                }
            }
            
            // Sort markers by time
            markers.sort((a, b) => a.time - b.time);
            candlestickSeries.setMarkers(markers);
        }
    } catch (e) {
        console.error("Error updating chart:", e);
    }
}

// Handle window resize
window.addEventListener('resize', () => {
    if (chart) {
        const container = document.getElementById('chart-container');
        chart.resize(container.clientWidth, 400);
    }
});

// --- Reset Button ---
document.getElementById('reset-btn').addEventListener('click', async () => {
    const confirmed = window.confirm(
        "⚠️ HARD RESET\n\n" +
        "This will:\n" +
        "1. Execute a Market SELL to flatten any open positions.\n" +
        "2. Wipe all trade history and experiment stats.\n" +
        "3. Restore Working Capital.\n\n" +
        "Are you sure you want to reset the experiment?"
    );
    if (!confirmed) return;

    try {
        const btn = document.getElementById('reset-btn');
        btn.innerText = 'Resetting...';
        btn.disabled = true;

        const res = await fetch('/api/reset', { method: 'POST' });
        if (res.ok) {
            // Clear the forecast line
            if (forecastSeries) forecastSeries.setData([]);
            // Immediately re-fetch state to refresh all UI panels
            await fetchState();
            await updateChartData();
            btn.innerText = 'Done!';
            setTimeout(() => {
                btn.innerText = 'Reset';
                btn.disabled = false;
            }, 2000);
        } else {
            btn.innerText = 'Error!';
            btn.disabled = false;
        }
    } catch (e) {
        console.error('Reset failed:', e);
        document.getElementById('reset-btn').innerText = 'Reset';
        document.getElementById('reset-btn').disabled = false;
    }
});

// --- Run Log / Trade History ---
let lastTradeCount = 0;

async function fetchRunLog() {
    try {
        const res = await fetch('/api/run_log');
        if (!res.ok) return;
        const data = await res.json();
        
        updateRunLogUI(data);
    } catch (e) {
        console.error("Error fetching run log:", e);
    }
}

function updateRunLogUI(data) {
    // Update run header
    document.getElementById('run-id-label').innerText = `Run ID: ${data.run_id}`;
    
    const summary = data.summary;
    const pnlEl = document.getElementById('run-summary-pnl');
    const pnl = summary.total_net_pnl || 0;
    pnlEl.innerText = `Total P/L: ${pnl >= 0 ? '+' : ''}$${pnl.toFixed(4)}`;
    pnlEl.style.color = pnl >= 0 ? 'var(--success)' : 'var(--danger)';
    pnlEl.style.background = pnl >= 0 ? 'rgba(0,255,136,0.1)' : 'rgba(255,51,102,0.1)';
    
    document.getElementById('run-summary-trades').innerText = 
        `${summary.total_trades} trade${summary.total_trades !== 1 ? 's' : ''} · ${summary.win_rate?.toFixed(0) || 0}% WR`;
    
    // Only re-render if trade count changed
    const trades = data.trades || [];
    if (trades.length === lastTradeCount) return;
    lastTradeCount = trades.length;
    
    const tbody = document.getElementById('trade-history-body');
    
    if (trades.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" style="padding: 1.5rem; text-align: center; color: var(--text-dim);">Awaiting first trade...</td></tr>';
        return;
    }
    
    const formatCurrency = (num) => num != null ? `$${parseFloat(num).toFixed(2)}` : '--';
    const formatHold = (secs) => {
        if (!secs) return '--';
        if (secs < 60) return `${secs}s`;
        return `${Math.floor(secs / 60)}m ${secs % 60}s`;
    };
    const triggerLabel = (trigger) => {
        const labels = {
            'brain': '🧠 Brain',
            'take_profit': '✅ Take Profit',
            'stop_loss': '🛡 Stop Loss',
            'circuit_breaker': '⚡ Circuit Breaker',
        };
        return labels[trigger] || trigger;
    };
    
    // Render newest first
    const rows = [...trades].reverse().map(trade => {
        const isWin = trade.outcome === 'WIN';
        const rowColor = isWin ? 'rgba(0,255,136,0.04)' : 'rgba(255,51,102,0.04)';
        const pnl = trade.net_profit || 0;
        const pnlStr = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(4)}`;
        const pnlColor = pnl >= 0 ? 'var(--success)' : 'var(--danger)';
        
        // Grab the brain's internal monologue at entry time
        const entryThought = trade.entry_metrics?.['Internal Monologue'] || '--';
        const truncatedThought = entryThought.length > 60 
            ? entryThought.substring(0, 60) + '...' 
            : entryThought;
        
        return `
            <tr style="background: ${rowColor}; border-bottom: 1px solid rgba(255,255,255,0.04);">
                <td style="padding: 0.6rem 0.8rem; color: var(--text-dim);">#${trade.trade_id}</td>
                <td style="padding: 0.6rem 0.8rem;">
                    <span style="color: ${isWin ? 'var(--success)' : 'var(--danger)'}; font-weight: 600;">
                        ${isWin ? '▲ WIN' : '▼ LOSS'}
                    </span>
                </td>
                <td style="padding: 0.6rem 0.8rem; font-family: monospace;">${formatCurrency(trade.entry_price)}</td>
                <td style="padding: 0.6rem 0.8rem; font-family: monospace;">${formatCurrency(trade.exit_price)}</td>
                <td style="padding: 0.6rem 0.8rem; color: ${pnlColor}; font-weight: 600; font-family: monospace;">${pnlStr}</td>
                <td style="padding: 0.6rem 0.8rem; color: var(--text-dim);">${formatHold(trade.hold_seconds)}</td>
                <td style="padding: 0.6rem 0.8rem; font-size: 0.8rem;">${triggerLabel(trade.exit_signal)}</td>
                <td style="padding: 0.6rem 0.8rem; font-size: 0.8rem; color: var(--accent-cyan);">${triggerLabel(trade.entry_signal)}</td>
                <td style="padding: 0.6rem 0.8rem; font-size: 0.75rem; color: var(--text-dim); font-style: italic;" title="${entryThought}">${truncatedThought}</td>
            </tr>
        `;
    }).join('');
    
    tbody.innerHTML = rows;
}

// Start everything
loadBrains();
setInterval(fetchState, updateInterval);
setInterval(fetchRunLog, 5000); // Refresh run log every 5s
fetchState(); // Initial fetch
fetchRunLog();
initChart();
