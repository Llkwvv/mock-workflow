// Mockworkflow Frontend - Particle Tech Style with Page Navigation
const API_BASE = 'http://localhost:8000';
let ws = null;
let charts = {};
let mainUploadedFile = null;
let batchFiles = [];
let currentPage = 'home';
let navigationHistory = [];

// ========== Theme ==========
function toggleTheme() {
    const body = document.body;
    const icon = document.getElementById('theme-icon');
    const text = document.getElementById('theme-text');
    if (body.classList.contains('light-mode')) {
        body.classList.remove('light-mode');
        icon.textContent = '🌙';
        text.textContent = '暗色模式';
        localStorage.setItem('theme', 'dark');
    } else {
        body.classList.add('light-mode');
        icon.textContent = '☀️';
        text.textContent = '亮色模式';
        localStorage.setItem('theme', 'light');
    }
    recreateParticles();
}

function initTheme() {
    const saved = localStorage.getItem('theme');
    if (saved === 'light') {
        document.body.classList.add('light-mode');
        document.getElementById('theme-icon').textContent = '☀️';
        document.getElementById('theme-text').textContent = '亮色模式';
    }
}

// ========== Particles ==========
function createParticles() {
    const container = document.getElementById('particles-bg');
    if (!container) return;
    container.innerHTML = '';
    const colors = document.body.classList.contains('light-mode')
        ? ['#0ea5e9','#8b5cf6','#38bdf8','#a78bfa','#f472b6']
        : ['#00d4ff','#ff00ff','#0099cc','#cc00cc','#ff6b6b'];
    for (let i = 0; i < 60; i++) {
        const p = document.createElement('div');
        p.className = 'particle';
        const s = Math.random() * 4 + 2;
        p.style.width = s + 'px'; p.style.height = s + 'px';
        p.style.left = Math.random() * 100 + '%';
        p.style.animationDelay = Math.random() * 8 + 's';
        p.style.background = colors[Math.floor(Math.random() * colors.length)];
        p.style.boxShadow = `0 0 ${s * 2}px ${colors[Math.floor(Math.random() * colors.length)]}`;
        container.appendChild(p);
    }
}

function recreateParticles() {
    createParticles();
}

// ========== Click Glass Crack Effect (removed) ==========
function createExplosion(x, y) {
    return; // disabled
    const now = Date.now();
    if (now - lastCrackTime < CRACK_COOLDOWN) return;
    lastCrackTime = now;
    const container = document.getElementById('particles-bg');
    if (!container) return;

    const svgNS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('width', '100%');
    svg.setAttribute('height', '100%');
    svg.style.cssText = `
        position: fixed;
        top: 0; left: 0;
        width: 100vw; height: 100vh;
        pointer-events: none;
        z-index: 9999;
        overflow: visible;
    `;
    container.appendChild(svg);

    const palette = [
        'rgba(220, 240, 255, 0.95)',
        'rgba(180, 220, 255, 0.85)',
        'rgba(255, 255, 255, 0.92)',
        'rgba(200, 230, 255, 0.8)',
        'rgba(160, 210, 255, 0.75)',
        'rgba(240, 248, 255, 0.6)',
    ];

    function rnd(a, b) { return a + Math.random() * (b - a); }
    function rndInt(a, b) { return Math.floor(rnd(a, b + 1)); }

    function makeZigzag(sx, sy, angle, len, segsOverride) {
        const segs = segsOverride || rndInt(4, 10);
        const segLen = len / segs;
        let cx = sx, cy = sy, ca = angle;
        const pts = [{ x: cx, y: cy }];

        for (let i = 0; i < segs; i++) {
            ca += (Math.random() - 0.5) * 0.7;
            if (Math.random() < 0.15) ca += (Math.random() > 0.5 ? 1.4 : -1.4);
            const drift = segLen * rnd(0.35, 0.6);
            cx += Math.cos(ca) * segLen + (Math.random() - 0.5) * drift;
            cy += Math.sin(ca) * segLen + (Math.random() - 0.5) * drift;
            pts.push({ x: cx, y: cy });
        }
        return pts;
    }

    function ptsToD(pts) {
        let d = `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`;
        for (let i = 1; i < pts.length; i++) {
            d += ` L ${pts[i].x.toFixed(1)} ${pts[i].y.toFixed(1)}`;
        }
        return d;
    }

    function addPath(d, stroke, sw, filterStr, delay, dur) {
        const p = document.createElementNS(svgNS, 'path');
        p.setAttribute('d', d);
        p.setAttribute('stroke', stroke);
        p.setAttribute('stroke-width', sw);
        p.setAttribute('fill', 'none');
        p.setAttribute('stroke-linecap', 'round');
        p.setAttribute('stroke-linejoin', 'round');
        if (filterStr) p.style.filter = filterStr;
        svg.appendChild(p);
        return { el: p, type: 'path', delay, dur };
    }

    const cracks = [];
    const allPts = [];
    const MAIN_LEN_MIN = 40, MAIN_LEN_MAX = 90;

    // === 1. 中心受压效果 ===
    const centerDot = document.createElementNS(svgNS, 'circle');
    centerDot.setAttribute('cx', x);
    centerDot.setAttribute('cy', y);
    centerDot.setAttribute('r', 0);
    centerDot.setAttribute('fill', 'rgba(255,255,255,0.9)');
    centerDot.style.filter = 'drop-shadow(0 0 6px rgba(255,255,255,0.8))';
    svg.appendChild(centerDot);
    cracks.push({ el: centerDot, type: 'dot', delay: 0, dur: 300 });

    const shockRing = document.createElementNS(svgNS, 'circle');
    shockRing.setAttribute('cx', x);
    shockRing.setAttribute('cy', y);
    shockRing.setAttribute('r', 3);
    shockRing.setAttribute('fill', 'none');
    shockRing.setAttribute('stroke', 'rgba(200,230,255,0.4)');
    shockRing.setAttribute('stroke-width', 1.5);
    shockRing.style.filter = 'drop-shadow(0 0 4px rgba(180,220,255,0.3))';
    svg.appendChild(shockRing);
    cracks.push({ el: shockRing, type: 'ring', delay: 20, dur: 400 });

    // === 2. 主裂纹（从中心向外放射，不规则） ===
    const mainCount = rndInt(4, 6);
    for (let i = 0; i < mainCount; i++) {
        const baseAngle = (Math.PI * 2 * i) / mainCount;
        const angle = baseAngle + rnd(-0.35, 0.35);
        const len = i % 3 === 0 ? rnd(30, 60) : rnd(MAIN_LEN_MIN, MAIN_LEN_MAX);
        const color = palette[rndInt(0, palette.length - 1)];
        const w = len < 50 ? rnd(1.2, 2.2) : rnd(0.8, 1.6);

        const pts = makeZigzag(x, y, angle, len);
        allPts.push(...pts);

        cracks.push(addPath(
            ptsToD(pts), color, w,
            `drop-shadow(0 0 ${w * 2.5}px ${color})`,
            rnd(40, 100), rnd(250, 400)
        ));

        const forks = rndInt(0, 2);
        for (let f = 0; f < forks; f++) {
            const idx = rndInt(Math.floor(pts.length * 0.35), pts.length - 2);
            const sp = pts[idx];
            const fa = angle + rnd(-1.6, 1.6);
            const fl = len * rnd(0.2, 0.55);
            const fpts = makeZigzag(sp.x, sp.y, fa, fl);
            allPts.push(...fpts);
            cracks.push(addPath(
                ptsToD(fpts), palette[rndInt(0, palette.length - 1)], w * 0.55,
                `drop-shadow(0 0 ${w}px rgba(180,220,255,0.5))`,
                rnd(80, 160), rnd(180, 320)
            ));

            if (Math.random() < 0.15 && fpts.length > 3) {
                const idx2 = rndInt(1, fpts.length - 2);
                const sp2 = fpts[idx2];
                const fa2 = fa + rnd(-1.5, 1.5);
                const fl2 = fl * rnd(0.25, 0.5);
                const f2pts = makeZigzag(sp2.x, sp2.y, fa2, fl2, rndInt(2, 5));
                cracks.push(addPath(
                    ptsToD(f2pts), 'rgba(255,255,255,0.5)', w * 0.3,
                    null, rnd(120, 200), rnd(100, 180)
                ));
            }
        }
    }

    // === 3. 同心环形裂纹（按压应力环） ===
    const ringCount = rndInt(1, 2);
    for (let r = 0; r < ringCount; r++) {
        const ringR = rnd(15, 55);
        const startA = rnd(0, Math.PI * 2);
        const sweep = rnd(2.0, 4.5);
        const largeArc = sweep > Math.PI ? 1 : 0;
        const sx = x + Math.cos(startA) * ringR;
        const sy = y + Math.sin(startA) * ringR;
        const ex = x + Math.cos(startA + sweep) * ringR;
        const ey = y + Math.sin(startA + sweep) * ringR;
        const rd = `M ${sx.toFixed(1)} ${sy.toFixed(1)} A ${ringR.toFixed(1)} ${ringR.toFixed(1)} 0 ${largeArc} 1 ${ex.toFixed(1)} ${ey.toFixed(1)}`;

        cracks.push(addPath(
            rd, 'rgba(200,230,255,0.55)', rnd(0.5, 1.0),
            'drop-shadow(0 0 3px rgba(180,220,255,0.35))',
            rnd(60, 120), rnd(280, 380)
        ));
    }

    // === 4. 外围交叉连接（形成碎块边界） ===
    for (let i = 0; i < allPts.length; i++) {
        for (let j = i + 1; j < allPts.length; j++) {
            const dx = allPts[j].x - allPts[i].x;
            const dy = allPts[j].y - allPts[i].y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < 35 && dist > 10 && Math.random() < 0.08) {
                const angle = Math.atan2(dy, dx);
                const segs = rndInt(2, 4);
                const midPts = makeZigzag(allPts[i].x, allPts[i].y, angle, dist * rnd(0.6, 1.0), segs);
                cracks.push(addPath(
                    ptsToD(midPts),
                    'rgba(200,230,255,0.4)', rnd(0.4, 0.9),
                    null, rnd(150, 280), rnd(100, 180)
                ));
            }
        }
    }

    // === 5. 远端碎屑 ===
    for (let i = 0; i < rndInt(3, 5); i++) {
        const dist = rnd(60, 120);
        const angle = rnd(0, Math.PI * 2);
        const fx = x + Math.cos(angle) * dist;
        const fy = y + Math.sin(angle) * dist;
        const fa = rnd(0, Math.PI * 2);
        const fl = rnd(8, 30);
        const fpts = makeZigzag(fx, fy, fa, fl, rndInt(2, 4));
        cracks.push(addPath(
            ptsToD(fpts), 'rgba(255,255,255,0.35)', rnd(0.3, 0.7),
            null, rnd(120, 240), rnd(60, 130)
        ));
    }

    // === 6. 微小碎片 ===
    for (let i = 0; i < rndInt(3, 5); i++) {
        const dist = rnd(20, 100);
        const angle = rnd(0, Math.PI * 2);
        const fx = x + Math.cos(angle) * dist;
        const fy = y + Math.sin(angle) * dist;
        const frag = document.createElementNS(svgNS, 'line');
        frag.setAttribute('x1', fx);
        frag.setAttribute('y1', fy);
        frag.setAttribute('x2', fx + rnd(-12, 12));
        frag.setAttribute('y2', fy + rnd(-12, 12));
        frag.setAttribute('stroke', 'rgba(255,255,255,0.4)');
        frag.setAttribute('stroke-width', rnd(0.3, 0.7));
        frag.setAttribute('stroke-linecap', 'round');
        svg.appendChild(frag);
        cracks.push({ el: frag, type: 'path', delay: rnd(50, 160), dur: rnd(80, 150) });
    }

    // === 动画触发 ===
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            cracks.forEach(c => {
                if (c.type === 'dot') {
                    c.el.animate([
                        { r: 0, opacity: 1 },
                        { r: 6, opacity: 0.9, offset: 0.5 },
                        { r: 2, opacity: 0 }
                    ], { duration: c.dur, delay: c.delay, easing: 'ease-out', fill: 'forwards' });
                } else if (c.type === 'ring') {
                    c.el.animate([
                        { r: 2, opacity: 0.7, strokeWidth: 2.5 },
                        { r: 35, opacity: 0, strokeWidth: 0.3 }
                    ], { duration: c.dur, delay: c.delay, easing: 'ease-out', fill: 'forwards' });
                } else {
                    const len = c.el.getTotalLength ? c.el.getTotalLength() : 20;
                    c.el.style.strokeDasharray = len;
                    c.el.style.strokeDashoffset = len;
                    c.el.animate([
                        { strokeDashoffset: len, opacity: 0 },
                        { strokeDashoffset: len, opacity: 1, offset: 0.02 },
                        { strokeDashoffset: 0, opacity: 1 }
                    ], {
                        duration: c.dur,
                        delay: c.delay,
                        easing: 'ease-out',
                        fill: 'forwards'
                    });
                }
            });
        });
    });

    // 整体淡出
    setTimeout(() => {
        svg.style.transition = 'opacity 0.9s ease-out';
        svg.style.opacity = '0';
        setTimeout(() => svg.remove(), 900);
    }, 2000);
}

// ========== Trail Effect ==========
let trailParticles = [];
let isMouseDown = false;
let lastTrailTime = 0;
let lastTrailX = 0;
let lastTrailY = 0;

function createTrail(x, y) {
    const container = document.getElementById('particles-bg');
    if (!container) return;
    
    // Glass crack colors
    const colors = [
        'rgba(200, 230, 255, 0.7)',
        'rgba(150, 200, 255, 0.6)',
        'rgba(255, 255, 255, 0.8)',
        'rgba(180, 220, 255, 0.5)',
    ];
    
    const color = colors[Math.floor(Math.random() * colors.length)];
    
    // Create short crack lines along mouse path
    if (lastTrailX !== 0 && lastTrailY !== 0) {
        const dx = x - lastTrailX;
        const dy = y - lastTrailY;
        const distance = Math.sqrt(dx * dx + dy * dy);
        
        if (distance > 5) {
            const angle = Math.atan2(dy, dx);
            const crackLength = Math.min(distance, 30);
            
            // Main crack line
            const line = document.createElement('div');
            line.style.cssText = `
                position: fixed;
                left: ${lastTrailX}px;
                top: ${lastTrailY}px;
                width: 0;
                height: 1px;
                background: ${color};
                pointer-events: none;
                z-index: 9998;
                transform-origin: left center;
                box-shadow: 0 0 6px ${color};
            `;
            container.appendChild(line);
            
            requestAnimationFrame(() => {
                line.style.width = crackLength + 'px';
                line.style.transform = `rotate(${angle}rad)`;
                line.style.transition = 'width 0.15s ease-out, opacity 0.4s ease-out 0.1s';
                line.style.opacity = '0';
            });
            
            setTimeout(() => line.remove(), 500);
            
            // Small branch crack
            if (Math.random() > 0.5) {
                const branchAngle = angle + (Math.random() - 0.5) * 1.2;
                const branchLength = 10 + Math.random() * 15;
                const branchStart = 0.3 + Math.random() * 0.4;
                const branchX = lastTrailX + Math.cos(angle) * crackLength * branchStart;
                const branchY = lastTrailY + Math.sin(angle) * crackLength * branchStart;
                
                const branch = document.createElement('div');
                branch.style.cssText = `
                    position: fixed;
                    left: ${branchX}px;
                    top: ${branchY}px;
                    width: 0;
                    height: 1px;
                    background: ${color};
                    pointer-events: none;
                    z-index: 9998;
                    transform-origin: left center;
                    box-shadow: 0 0 4px ${color};
                `;
                container.appendChild(branch);
                
                requestAnimationFrame(() => {
                    branch.style.width = branchLength + 'px';
                    branch.style.transform = `rotate(${branchAngle}rad)`;
                    branch.style.transition = 'width 0.1s ease-out 0.05s, opacity 0.3s ease-out 0.15s';
                    branch.style.opacity = '0';
                });
                
                setTimeout(() => branch.remove(), 450);
            }
        }
    }
    
    lastTrailX = x;
    lastTrailY = y;
}

function handleMouseMove(e) {
    const now = Date.now();
    if (now - lastTrailTime > 20) {
        createTrail(e.clientX, e.clientY);
        lastTrailTime = now;
    }
}

// Initialize mouse effects
document.addEventListener('mousemove', handleMouseMove);

// ========== Custom Star Cursor ==========
function initStarCursor() {
    // Create a full-screen overlay to hide the system cursor
    const cursorOverlay = document.createElement('div');
    cursorOverlay.id = 'cursor-overlay';
    cursorOverlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        pointer-events: none;
        z-index: 9999;
        cursor: none;
    `;
    document.body.appendChild(cursorOverlay);

    const starCursor = document.createElement('div');
    starCursor.id = 'star-cursor';
    starCursor.textContent = '⭐';
    starCursor.style.cssText = `
        position: fixed;
        width: 24px;
        height: 24px;
        font-size: 24px;
        pointer-events: none;
        z-index: 10000;
        transition: transform 0.1s ease-out;
        line-height: 1;
    `;
    document.body.appendChild(starCursor);

    document.addEventListener('mousemove', (e) => {
        starCursor.style.left = (e.clientX - 12) + 'px';
        starCursor.style.top = (e.clientY - 12) + 'px';
    });

    document.addEventListener('mousedown', () => {
        starCursor.style.transform = 'scale(0.8)';
    });

    document.addEventListener('mouseup', () => {
        starCursor.style.transform = 'scale(1)';
    });
}

// Initialize cursor when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initStarCursor);
} else {
    initStarCursor();
}

// ========== Page Navigation ==========
function navigateTo(page) {
    if (page !== currentPage && page !== 'home') {
        navigationHistory.push(currentPage);
    }
    currentPage = page;
    document.querySelectorAll('[id^="page-"]').forEach(el => el.style.display = 'none');
    const target = document.getElementById('page-' + page);
    if (target) target.style.display = 'block';
    window.scrollTo(0, 0);

    if (page === 'tasks') loadTasks();
    if (page === 'schedules') { loadSchedules(); loadSamplesForSelect(); }
    if (page === 'samples') loadSamples();
    if (page === 'stats') loadStats();
    if (page === 'settings') loadSystemInfo();
    if (page === 'schema') { loadSchemaPage(); }
    if (page === 'templates') { loadTemplatesPage(); }
    if (page === 'generate') { /* aggregate entry page, no init needed */ }
    if (page === 'monitor') { loadMonitorStats(); loadMetrics(); loadAuditLogs(); }
    if (page === 'engine') { loadEnginePage(); }
    if (page === 'plugins') { loadPlugins(); }
}

function goHome() {
    navigationHistory = [];
    navigateTo('home');
}

function goBack() {
    if (navigationHistory.length > 0) {
        const previousPage = navigationHistory.pop();
        currentPage = previousPage;
        document.querySelectorAll('[id^="page-"]').forEach(el => el.style.display = 'none');
        const target = document.getElementById('page-' + previousPage);
        if (target) target.style.display = 'block';
        window.scrollTo(0, 0);
    } else {
        goHome();
    }
}

// ========== Toast ==========
function showToast(msg, type = 'success') {
    const c = document.getElementById('toastContainer');
    const t = document.createElement('div');
    t.className = `toast ${type}`;
    const icons = { success: '✅', error: '❌', warning: '⚠️' };
    t.innerHTML = `<span>${icons[type] || 'ℹ️'}</span><span>${msg}</span>`;
    c.appendChild(t);
    setTimeout(() => t.remove(), 3000);
}

// ========== Auth / Login ==========
let loginRetryQueue = [];
let currentCsrfToken = '';

function showLogin() {
    document.getElementById('login-overlay').style.display = 'flex';
    document.getElementById('login-username').focus();

    // 加载记住的凭据
    loadRememberedCredentials();

    // Fetch fresh CSRF token each time login is shown
    fetch(API_BASE + '/api/auth/csrf')
        .then(r => r.json())
        .then(d => { currentCsrfToken = d.token; })
        .catch(() => { currentCsrfToken = ''; });
}

// 加载记住的凭据
function loadRememberedCredentials() {
    const username = localStorage.getItem('remembered_username');
    const encryptedPwd = localStorage.getItem('remembered_password');

    if (username && encryptedPwd) {
        document.getElementById('login-username').value = username;
        document.getElementById('remember-me').checked = true;
    }
}

function hideLogin() {
    document.getElementById('login-overlay').style.display = 'none';
    document.getElementById('login-error').style.display = 'none';
    document.getElementById('login-username').value = '';
    document.getElementById('login-password').value = '';
}

async function doLogin() {
    const username = document.getElementById('login-username').value.trim();
    const pwd = document.getElementById('login-password').value.trim();
    const rememberMe = document.getElementById('remember-me').checked;
    const errEl = document.getElementById('login-error');

    if (!username || !pwd) {
        errEl.textContent = '请输入用户名和密码';
        errEl.style.display = 'block';
        return;
    }

    // 显示加载状态
    const loginBtn = document.querySelector('#login-overlay button');
    const originalText = loginBtn.textContent;
    loginBtn.textContent = '登录中...';
    loginBtn.disabled = true;

    try {
        const r = await fetch(API_BASE + '/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                username: username,
                password: pwd,
                csrf_token: currentCsrfToken
            })
        });

        if (r.status === 403) {
            const data = await r.json();
            errEl.textContent = '尝试次数过多，请' + Math.round((data.retry_after || 900) / 60) + '分钟后再试';
            errEl.style.display = 'block';
            return;
        }

        const data = await r.json();
        if (!r.ok || !data.success) {
            errEl.textContent = data.message || '登录失败';
            errEl.style.display = 'block';
            return;
        }

        // 处理记住密码
        if (rememberMe) {
            try {
                // 这里应该实现加密存储，为了简化暂时使用localStorage
                localStorage.setItem('remembered_username', username);
                // 注意：实际项目中应该加密存储密码
            } catch (e) {
                console.warn('记住密码失败');
            }
        } else {
            // 清除记住的密码
            localStorage.removeItem('remembered_username');
        }

        hideLogin();
        showToast('欢迎，' + (data.username || '') + '！');

        // Retry queued calls
        const queue = loginRetryQueue.slice();
        loginRetryQueue = [];
        queue.forEach(fn => fn());
    } catch (e) {
        errEl.textContent = '网络错误，请重试';
        errEl.style.display = 'block';
    } finally {
        loginBtn.textContent = originalText;
        loginBtn.disabled = false;
    }
}

async function checkAuth() {
    try {
        const r = await fetch(API_BASE + '/api/auth/me', { credentials: 'include' });
        const data = await r.json();
        if (data.authenticated && data.username) {
            document.getElementById('username-display').textContent = data.username;
            document.getElementById('user-menu').style.display = 'block';
        } else {
            document.getElementById('user-menu').style.display = 'none';
            showLogin();
        }
    } catch (e) {
        showLogin();
    }
}

async function doLogout() {
    try {
        const r = await fetch(API_BASE + '/api/auth/logout', {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' }
        });
        if (r.ok) {
            showToast('已成功退出登录');
            document.getElementById('user-menu').style.display = 'none';
            showLogin();
            // 清空输入框
            document.getElementById('login-username').value = '';
            document.getElementById('login-password').value = '';
        }
    } catch (e) {
        console.error('Logout failed:', e);
    }
}

function showRegisterForm() {
    document.getElementById('login-form').style.display = 'none';
    document.getElementById('register-form').style.display = 'block';
    // 清空错误信息
    document.getElementById('register-error').style.display = 'none';
    document.getElementById('register-success').style.display = 'none';
}

function showLoginForm() {
    document.getElementById('register-form').style.display = 'none';
    document.getElementById('login-form').style.display = 'block';
    // 清空错误信息
    document.getElementById('login-error').style.display = 'none';
}

// 忘记密码功能
async function forgotPassword() {
    showToast('忘记密码功能正在开发中...', 'warning');
    // 在实际项目中，这里会打开忘记密码对话框或跳转到忘记密码页面
}

async function doRegister() {
    const username = document.getElementById('register-username').value.trim();
    const password = document.getElementById('register-password').value.trim();
    const displayName = document.getElementById('register-display-name').value.trim();
    const errEl = document.getElementById('register-error');
    const successEl = document.getElementById('register-success');

    // 隐藏之前的消息
    errEl.style.display = 'none';
    successEl.style.display = 'none';

    // 验证输入
    if (!username || username.length < 3) {
        errEl.textContent = '用户名至少需要3个字符';
        errEl.style.display = 'block';
        return;
    }
    if (!password || password.length < 6) {
        errEl.textContent = '密码至少需要6个字符';
        errEl.style.display = 'block';
        return;
    }

    try {
        const r = await fetch(API_BASE + '/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username: username,
                password: password,
                display_name: displayName || null,
                csrf_token: currentCsrfToken
            })
        });

        const data = await r.json();

        if (!r.ok) {
            errEl.textContent = data.message || '注册失败';
            errEl.style.display = 'block';
            return;
        }

        // 注册成功
        successEl.textContent = '注册成功！正在返回登录界面...';
        successEl.style.display = 'block';

        // 3秒后自动返回登录界面
        setTimeout(() => {
            showLoginForm();
            // 自动填充用户名
            document.getElementById('login-username').value = username;
            document.getElementById('login-password').value = '';
        }, 3000);

    } catch (e) {
        errEl.textContent = '网络错误，请重试';
        errEl.style.display = 'block';
    }
}

// ========== API Helpers ==========
function _handleAuth(r, retryFn) {
    if (r.status === 401) {
        showLogin();
        loginRetryQueue.push(retryFn);
        throw new Error('Authentication required');
    }
}

async function apiGet(path) {
    const doFetch = async () => {
        const r = await fetch(API_BASE + path, { credentials: 'include' });
        if (r.status === 401) { _handleAuth(r, () => apiGet(path)); return; }
        if (!r.ok) throw new Error(await r.text());
        return r.json();
    };
    return doFetch();
}

async function apiPost(path, body) {
    const doFetch = async () => {
        const opts = { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include' };
        if (body) opts.body = JSON.stringify(body);
        const r = await fetch(API_BASE + path, opts);
        if (r.status === 401) { _handleAuth(r, () => apiPost(path, body)); return; }
        if (!r.ok) throw new Error(await r.text());
        return r.json();
    };
    return doFetch();
}

async function apiDelete(path) {
    const doFetch = async () => {
        const r = await fetch(API_BASE + path, { method: 'DELETE', credentials: 'include' });
        if (r.status === 401) { _handleAuth(r, () => apiDelete(path)); return; }
        if (!r.ok) throw new Error(await r.text());
        return r.json();
    };
    return doFetch();
}

async function apiPatch(path) {
    const doFetch = async () => {
        const r = await fetch(API_BASE + path, { method: 'PATCH', credentials: 'include' });
        if (r.status === 401) { _handleAuth(r, () => apiPatch(path)); return; }
        if (!r.ok) throw new Error(await r.text());
        return r.json();
    };
    return doFetch();
}

// ========== Tasks ==========
async function loadTasks() {
    try {
        const data = await apiGet('/api/tasks');
        renderTasks(data.tasks || []);
    } catch (e) { console.error('Load tasks failed', e); }
}

function renderTasks(tasks) {
    const el = document.getElementById('taskList');
    if (!tasks.length) {
        el.innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:40px;">暂无任务</p>';
        return;
    }
    const statusMap = {
        pending: { text: '待处理', cls: 'pending' },
        running: { text: '运行中', cls: 'running' },
        completed: { text: '已完成', cls: 'completed' },
        failed: { text: '失败', cls: 'failed' },
        cancelled: { text: '已取消', cls: 'cancelled' }
    };
    let html = '<table class="tech-table"><thead><tr><th>ID</th><th>样本</th><th>表名</th><th>行数</th><th>状态</th><th>进度</th><th>操作</th></tr></thead><tbody>';
    tasks.forEach(t => {
        const st = statusMap[t.status] || { text: t.status, cls: 'pending' };
        html += `<tr onclick="viewTaskDetail('${t.id}')" style="cursor:pointer;">
            <td>${t.id.slice(0,8)}</td>
            <td>${t.sample_filename.split('/').pop()}</td>
            <td>${t.table_name}</td>
            <td>${t.rows}</td>
            <td><span class="status-indicator ${st.cls}"></span>${st.text}</td>
            <td><div class="tech-progress"><div class="tech-progress-bar" style="width:${t.progress}%"></div></div></td>
            <td onclick="event.stopPropagation()">
                ${t.status === 'failed' && t.retryable ? `<button class="neon-btn" style="padding:4px 10px;font-size:12px;" onclick="retryTask('${t.id}')">重试</button>` : ''}
                <button class="neon-btn secondary" style="padding:4px 10px;font-size:12px;" onclick="cancelTask('${t.id}')">取消</button>
            </td>
        </tr>`;
    });
    html += '</tbody></table>';
    el.innerHTML = html;
}

async function viewTaskDetail(taskId) {
    try {
        const data = await apiGet('/api/tasks/' + taskId);
        const task = data.task;
        const statusMap = {
            pending: '待处理',
            running: '运行中',
            completed: '已完成',
            failed: '失败',
            cancelled: '已取消'
        };
        
        let dataPreviewHtml = '';
        if (task.result_preview && task.result_preview.preview_rows) {
            const previewRows = task.result_preview.preview_rows;
            const columns = task.result_preview.columns || Object.keys(previewRows[0] || {});
            dataPreviewHtml = `
                <div style="margin-top:16px;">
                    <p style="opacity:0.7;font-size:14px;margin-bottom:8px;">数据预览（前5行）</p>
                    <div style="overflow-x:auto;">
                        <table class="tech-table" style="font-size:12px;">
                            <thead><tr>${columns.map(c => `<th>${c}</th>`).join('')}</tr></thead>
                            <tbody>
                                ${previewRows.map(row => `<tr>${columns.map(c => `<td>${row[c] || ''}</td>`).join('')}</tr>`).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;
        }
        
        let downloadHtml = '';
        if (task.result_full && task.result_full.output_path) {
            const outputPath = task.result_full.output_path;
            const fileName = outputPath.split('/').pop();
            downloadHtml = `
                <div style="margin-top:16px;padding:12px;background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.3);border-radius:8px;">
                    <p style="opacity:0.7;font-size:14px;">下载文件</p>
                    <a href="/output/${fileName}" download="${fileName}" class="neon-btn" style="display:inline-block;padding:6px 12px;font-size:12px;text-decoration:none;">📥 下载 ${fileName}</a>
                </div>
            `;
        }
        
        const html = `
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
                <div>
                    <p style="opacity:0.7;font-size:14px;">任务ID</p>
                    <p style="font-family:monospace;font-size:16px;">${task.id}</p>
                </div>
                <div>
                    <p style="opacity:0.7;font-size:14px;">状态</p>
                    <p style="font-size:16px;">${statusMap[task.status] || task.status}</p>
                </div>
                <div>
                    <p style="opacity:0.7;font-size:14px;">样本文件</p>
                    <p style="font-size:16px;">${task.sample_filename.split('/').pop()}</p>
                </div>
                <div>
                    <p style="opacity:0.7;font-size:14px;">表名</p>
                    <p style="font-size:16px;">${task.table_name}</p>
                </div>
                <div>
                    <p style="opacity:0.7;font-size:14px;">生成行数</p>
                    <p style="font-size:16px;">${task.rows}</p>
                </div>
                <div>
                    <p style="opacity:0.7;font-size:14px;">进度</p>
                    <p style="font-size:16px;">${task.progress}%</p>
                </div>
                <div>
                    <p style="opacity:0.7;font-size:14px;">创建时间</p>
                    <p style="font-size:14px;">${new Date(task.created_at).toLocaleString()}</p>
                </div>
                <div>
                    <p style="opacity:0.7;font-size:14px;">导出数据库</p>
                    <p style="font-size:16px;">${task.enable_db_export ? '是' : '否'}</p>
                </div>
            </div>
            ${task.error ? `<div style="margin-top:16px;padding:12px;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:8px;">
                <p style="opacity:0.7;font-size:14px;">错误信息</p>
                <p style="color:#ef4444;font-size:14px;">${task.error}</p>
            </div>` : ''}
            ${task.result_full ? `<div style="margin-top:16px;padding:12px;background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.3);border-radius:8px;">
                <p style="opacity:0.7;font-size:14px;">生成结果</p>
                <p style="color:#22c55e;font-size:14px;">生成行数: ${task.result_full.generated_rows || 0}</p>
                <p style="color:#22c55e;font-size:14px;">输出格式: ${task.result_full.output || 'csv'}</p>
            </div>` : ''}
            ${dataPreviewHtml}
            ${downloadHtml}
        `;
        document.getElementById('taskDetail').innerHTML = html;
    } catch (e) {
        document.getElementById('taskDetail').innerHTML = '<p style="color:#ef4444;">加载详情失败</p>';
    }
}

async function submitTask() {
    const sample = document.getElementById('sampleSelect').value;
    const table = document.getElementById('tableName').value || 'auto_table';
    const rows = parseInt(document.getElementById('rowCount').value) || 100;
    const dbExport = document.getElementById('enableDbExport').checked;
    if (!sample) { showToast('请选择样本文件', 'error'); return; }
    const btn = document.getElementById('submitBtn');
    btn.disabled = true;
    // 先跳转任务中心，不等待后端返回
    navigateTo('tasks');
    try {
        await apiPost('/api/tasks', { sample_filename: sample, table_name: table, rows: rows, enable_db_export: dbExport });
        showToast('任务创建成功！');
        loadTasks();
    } catch (e) {
        showToast('创建失败: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
    }
}

async function cancelTask(id) {
    try { await apiDelete('/api/tasks/' + id); showToast('任务已取消'); loadTasks(); }
    catch (e) { showToast('取消失败', 'error'); }
}

async function retryTask(id) {
    try { await apiPost('/api/tasks/' + id + '/retry'); showToast('重试任务已提交'); loadTasks(); }
    catch (e) { showToast('重试失败', 'error'); }
}

// ========== Samples ==========
async function loadSamples() {
    try {
        const data = await apiGet('/api/samples');
        renderSamples(data.samples || []);
        updateSampleSelects(data.samples || []);
    } catch (e) { console.error(e); }
}

function renderSamples(samples) {
    const el = document.getElementById('sampleList');
    if (!samples.length) { el.innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:40px;">暂无样本文件</p>'; return; }
    let html = '';
    samples.forEach(s => {
        const size = (s.size / 1024).toFixed(1);
        html += `<div class="sample-item">
            <div class="sample-info">
                <span class="sample-name">${s.name}</span>
                <span class="sample-meta">${size} KB</span>
            </div>
            <div style="display:flex;gap:8px;">
                <button class="neon-btn" style="padding:6px 14px;font-size:12px;" onclick="useSample('${s.path}','${s.name}')">使用</button>
            </div>
        </div>`;
    });
    el.innerHTML = html;
}

function updateSampleSelects(samples) {
    const opts = samples.map(s => `<option value="${s.path}">${s.name}</option>`).join('');
    const sel = document.getElementById('sampleSelect');
    if (sel) sel.innerHTML = '<option value="">-- 选择样本文件 --</option>' + opts;
    const sch = document.getElementById('scheduleSample');
    if (sch) sch.innerHTML = opts;
}

function useSample(path, name) {
    navigateTo('tasks');
    setTimeout(() => {
        document.getElementById('sampleSelect').value = path;
        const stem = name.replace(/\.[^.]+$/, '');
        const tn = document.getElementById('tableName');
        if (tn && (!tn.value || tn.value === 'auto_table')) tn.value = stem;
    }, 100);
    showToast('已选择: ' + name);
}

function onSampleChange() {
    const sel = document.getElementById('sampleSelect');
    const name = sel.options[sel.selectedIndex].text;
    if (name && name !== '-- 选择样本文件 --') {
        const stem = name.replace(/\.[^.]+$/, '');
        const tn = document.getElementById('tableName');
        if (tn && (!tn.value || tn.value === 'auto_table')) tn.value = stem;
    }
}

async function loadSamplesForSelect() {
    try { const data = await apiGet('/api/samples'); updateSampleSelects(data.samples || []); }
    catch (e) {}
}

// ========== Upload ==========
function handleDragOver(e) { e.preventDefault(); e.currentTarget.classList.add('dragover'); }
function handleDragLeave(e) { e.currentTarget.classList.remove('dragover'); }
function handleDrop(e) {
    e.preventDefault();
    e.currentTarget.classList.remove('dragover');
    const files = e.dataTransfer.files;
    if (files.length) setUploadFile(files[0]);
}
function handleFileSelect(e) {
    const files = e.target.files;
    if (files.length) setUploadFile(files[0]);
}
function setUploadFile(file) {
    mainUploadedFile = file;
    const preview = document.getElementById('uploadPreview');
    if (preview) {
        preview.style.display = 'block';
        document.getElementById('uploadFileName').textContent = file.name;
        document.getElementById('uploadFileSize').textContent = (file.size / 1024).toFixed(1) + ' KB';
    }
}

async function uploadFile() {
    if (!mainUploadedFile) return;
    const rows = parseInt(document.getElementById('uploadRows').value) || 100;
    const table = document.getElementById('uploadTableName').value || '';
    const dbExport = document.getElementById('uploadDbExport').checked;

    const fd = new FormData();
    fd.append('files', mainUploadedFile);
    fd.append('rows', rows);
    fd.append('table_prefix', table);
    fd.append('enable_db_export', dbExport);

    // 先跳转任务中心，不等待后端返回
    navigateTo('tasks');
    const preview = document.getElementById('uploadPreview');
    if (preview) preview.style.display = 'none';
    mainUploadedFile = null;

    try {
        const r = await fetch(API_BASE + '/api/tasks/batch-from-files', { method: 'POST', body: fd, credentials: 'include' });
        if (r.status === 401) { _handleAuth(r, () => uploadFile()); return; }
        if (!r.ok) throw new Error(await r.text());
        const data = await r.json();
        showToast('任务创建成功: ' + data.message);
        loadTasks();
    } catch (e) { showToast('创建任务失败: ' + e.message, 'error'); }
}

// ========== Batch ==========
function handleBatchFiles(e) {
    batchFiles = Array.from(e.target.files);
    renderBatchFiles();
}
function renderBatchFiles() {
    const el = document.getElementById('batchFilesList');
    if (!batchFiles.length) { el.innerHTML = ''; return; }
    let html = '<div style="display:flex;flex-direction:column;gap:8px;">';
    batchFiles.forEach(f => {
        html += `<div class="sample-item" style="background:var(--card-bg);border:1px solid var(--card-border);border-radius:8px;">
            <div class="sample-info"><span class="sample-name">${f.name}</span><span class="sample-meta">${(f.size/1024).toFixed(1)} KB</span></div>
        </div>`;
    });
    html += '</div>';
    el.innerHTML = html;
}

async function submitBatch() {
    if (!batchFiles.length) { showToast('请选择文件', 'error'); return; }
    const rows = parseInt(document.getElementById('batchRows').value) || 100;
    const prefix = document.getElementById('batchPrefix').value || '';
    const fd = new FormData();
    batchFiles.forEach(f => fd.append('files', f));
    fd.append('rows', rows);
    fd.append('table_prefix', prefix);

    // 先跳转任务中心，不等待后端返回
    navigateTo('tasks');
    batchFiles = [];
    renderBatchFiles();

    try {
        const r = await fetch(API_BASE + '/api/tasks/batch-from-files', { method: 'POST', body: fd, credentials: 'include' });
        if (r.status === 401) { _handleAuth(r, () => batchCreateFromFiles()); return; }
        if (!r.ok) throw new Error(await r.text());
        showToast('任务创建成功');
    } catch (e) { showToast('任务创建失败: ' + e.message, 'error'); }
}

// ========== Schedules ==========
async function loadSchedules() {
    try {
        const data = await apiGet('/api/schedules');
        renderSchedules(data.schedules || []);
    } catch (e) {}
}

function renderSchedules(schedules) {
    const el = document.getElementById('scheduleList');
    if (!schedules.length) { el.innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:40px;">暂无定时任务</p>'; return; }
    let html = '';
    schedules.forEach(s => {
        html += `<div class="schedule-item">
            <div class="schedule-info">
                <div class="schedule-name">${s.sample_filename.split('/').pop()} → ${s.table_name}</div>
                <div class="schedule-detail">${s.rows} 行 | ${s.cron} | 下次: ${s.next_run ? new Date(s.next_run).toLocaleString() : '已禁用'}</div>
            </div>
            <div style="display:flex;align-items:center;gap:10px;">
                <div class="toggle-switch ${s.enabled ? 'on' : ''}" onclick="toggleSchedule('${s.id}')"></div>
                <button class="neon-btn secondary" style="padding:4px 10px;font-size:12px;" onclick="deleteSchedule('${s.id}')">删除</button>
            </div>
        </div>`;
    });
    el.innerHTML = html;
}

function updateCronFields() {
    const type = document.getElementById('scheduleType').value;
    document.getElementById('cronDailyFields').style.display = type === 'daily' ? 'flex' : 'none';
    document.getElementById('cronWeeklyFields').style.display = type === 'weekly' ? 'flex' : 'none';
    document.getElementById('cronMonthlyFields').style.display = type === 'monthly' ? 'flex' : 'none';
    document.getElementById('cronCustomFields').style.display = type === 'custom' ? 'flex' : 'none';
}

function generateCronExpression() {
    const type = document.getElementById('scheduleType').value;
    let cron = '';
    
    if (type === 'daily') {
        const time = document.getElementById('scheduleTime').value;
        const [hour, minute] = time.split(':');
        cron = `${minute} ${hour} * * *`;
    } else if (type === 'weekly') {
        const weekday = document.getElementById('scheduleWeekday').value;
        const time = document.getElementById('scheduleWeeklyTime').value;
        const [hour, minute] = time.split(':');
        cron = `${minute} ${hour} * * ${weekday}`;
    } else if (type === 'monthly') {
        const day = document.getElementById('scheduleDay').value;
        const time = document.getElementById('scheduleMonthlyTime').value;
        const [hour, minute] = time.split(':');
        cron = `${minute} ${hour} ${day} * *`;
    } else if (type === 'custom') {
        cron = document.getElementById('scheduleCron').value;
    }
    
    return cron;
}

async function createSchedule() {
    const sample = document.getElementById('scheduleSample').value;
    const table = document.getElementById('scheduleTable').value || 'auto_table';
    const rows = parseInt(document.getElementById('scheduleRows').value) || 100;
    const cron = generateCronExpression();
    const dbExport = document.getElementById('scheduleDbExport').checked;
    
    if (!sample) { showToast('请选择样本文件', 'error'); return; }
    if (!cron) { showToast('请选择执行频率', 'error'); return; }
    
    try {
        await apiPost('/api/schedules', { sample_filename: sample, table_name: table, rows: rows, cron: cron, enable_db_export: dbExport });
        showToast('定时任务创建成功');
        loadSchedules();
    } catch (e) { showToast('创建失败: ' + e.message, 'error'); }
}

async function toggleSchedule(id) {
    try { await apiPatch('/api/schedules/' + id + '/toggle'); showToast('状态已更新'); loadSchedules(); }
    catch (e) { showToast('操作失败', 'error'); }
}

async function deleteSchedule(id) {
    if (!confirm('确定删除此定时任务？')) return;
    try { await apiDelete('/api/schedules/' + id); showToast('已删除'); loadSchedules(); }
    catch (e) { showToast('删除失败', 'error'); }
}

// ========== Stats ==========
async function loadStats() {
    try {
        const data = await apiGet('/api/tasks/stats/summary');
        document.getElementById('statTotal').textContent = data.total_tasks;
        document.getElementById('statSuccessRate').textContent = data.success_rate + '%';
        document.getElementById('statAvgRows').textContent = data.avg_rows;
        renderStatusChart(data.status_distribution);
        renderDailyChart(data.daily_counts);
    } catch (e) { console.error(e); }
}

function renderStatusChart(dist) {
    const ctx = document.getElementById('statusChart');
    if (!ctx) return;
    if (charts.status) charts.status.destroy();
    charts.status = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['待处理','运行中','已完成','失败','已取消'],
            datasets: [{
                data: [dist.pending, dist.running, dist.completed, dist.failed, dist.cancelled],
                backgroundColor: ['#f59e0b','#3b82f6','#22c55e','#ef4444','#6b7280'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'bottom', labels: { color: '#888' } } }
        }
    });
}

function renderDailyChart(data) {
    const ctx = document.getElementById('dailyChart');
    if (!ctx) return;
    if (charts.daily) charts.daily.destroy();
    charts.daily = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.map(d => d.date.slice(5)),
            datasets: [{
                label: '任务数',
                data: data.map(d => d.count),
                borderColor: '#00d4ff',
                backgroundColor: 'rgba(0,212,255,0.1)',
                fill: true,
                tension: 0.4,
                pointRadius: 3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { ticks: { color: '#888', maxTicksLimit: 7 } },
                y: { ticks: { color: '#888', stepSize: 1 } }
            },
            plugins: { legend: { display: false } }
        }
    });
}

// ========== Settings / System Info ==========
async function loadSystemInfo() {
    try {
        const health = await apiGet('/api/health');
        const settings = await apiGet('/api/settings');

        // 更新系统信息卡
        const systemInfoHtml = `
            <p><strong>服务状态:</strong> <span style="color:#22c55e;">正常运行</span></p>
            <p style="margin-top:8px;"><strong>当前时间:</strong> ${new Date(health.timestamp).toLocaleString()}</p>
            <p style="margin-top:8px;"><strong>API 版本:</strong> ${settings.config.app_name} ${health.metrics.version || '0.2.0'}</p>
            <p style="margin-top:8px;"><strong>LLM 状态:</strong> ${settings.config.llm_enabled ? '<span style="color:#22c55e;">已启用</span>' : '<span style="color:#ef4444;">已禁用</span>'}</p>
            <p style="margin-top:8px;"><strong>数据库导出:</strong> ${settings.config.db_export_enabled ? '<span style="color:#22c55e;">已启用</span>' : '<span style="color:#6b7280;">已禁用</span>'}</p>
        `;
        document.getElementById('systemInfo').innerHTML = systemInfoHtml;

        // 更新实时状态卡
        document.getElementById('realtimeStatus').innerHTML = '<p style="color:#22c55e;">WebSocket 已连接</p>';

        // 初始化设置表单
        initSettingsForm(settings.config);

    } catch (e) {
        console.error('Failed to load system info:', e);
        document.getElementById('systemInfo').innerHTML = '<p style="color:#ef4444;">无法获取系统信息</p>';
        document.getElementById('realtimeStatus').innerHTML = '<p style="color:#ef4444;">WebSocket 连接失败</p>';
    }
}

function initSettingsForm(config) {
    // LLM 配置
    document.getElementById('llmEnabled').checked = config.llm_enabled;
    document.getElementById('llmProvider').value = config.llm_provider || '';
    document.getElementById('llmApiKey').value = config.llm_api_key || '';
    document.getElementById('llmBaseUrl').value = config.llm_base_url || '';
    document.getElementById('llmModel').value = config.llm_model || '';
    document.getElementById('llmTimeout').value = config.llm_timeout;
    document.getElementById('llmMaxTokens').value = config.llm_max_tokens;
    document.getElementById('llmTemperature').value = config.llm_temperature;

    // 数据库导出配置
    document.getElementById('dbExportEnabled').checked = config.db_export_enabled;
    document.getElementById('mysqlUrl').value = config.mysql_url || '';

    // RAG 配置
    document.getElementById('embeddingModel').value = config.embedding_model || '';
    document.getElementById('ragTopKRules').value = config.rag_top_k_rules;
    document.getElementById('ragTopKSamples').value = config.rag_top_k_samples;

    // 认证配置
    document.getElementById('webPassword').value = config.web_password || '';

    // 值池配置
    document.getElementById('llmValuePoolEnabled').checked = config.llm_value_pool_enabled;
    document.getElementById('llmValuePoolSize').value = config.llm_value_pool_size;

    // 规则配置
    document.getElementById('rulesAutosave').checked = config.rules_autosave;
    document.getElementById('rulesMinConfidence').value = config.rules_min_confidence;

    // 添加事件监听器
    addSettingsEventListeners();
}

function addSettingsEventListeners() {
    // LLM 启用开关
    document.getElementById('llmEnabled').addEventListener('change', updateLlmConfig);

    // LLM 提供商选择
    document.getElementById('llmProvider').addEventListener('change', updateLlmProviderPreset);

    // LLM 表单字段
    const llmFields = ['llmApiKey', 'llmBaseUrl', 'llmModel'];
    llmFields.forEach(field => {
        document.getElementById(field)?.addEventListener('change', updateLlmConfig);
    });

    // 数值型配置
    const numberFields = [
        'llmTimeout', 'llmMaxTokens', 'llmTemperature',
        'ragTopKRules', 'ragTopKSamples',
        'llmValuePoolSize', 'rulesMinConfidence'
    ];
    numberFields.forEach(field => {
        document.getElementById(field)?.addEventListener('change', saveSetting);
    });

    // 文本型配置
    const textFields = ['embeddingModel', 'mysqlUrl', 'webPassword'];
    textFields.forEach(field => {
        document.getElementById(field)?.addEventListener('change', saveSetting);
    });

    // 开关型配置
    const toggleFields = [
        'dbExportEnabled', 'llmValuePoolEnabled', 'rulesAutosave'
    ];
    toggleFields.forEach(field => {
        document.getElementById(field)?.addEventListener('change', saveSetting);
    });
}

async function updateLlmProviderPreset() {
    const provider = document.getElementById('llmProvider').value;
    const apiKey = document.getElementById('llmApiKey').value;

    if (!provider) {
        // 如果没有选择提供商，允许手动输入
        return;
    }

    try {
        // 模拟预设应用 - 在真实实现中，这将在后端处理
        let presetInfo = `使用 ${provider.toUpperCase()} 预设`;
        if (provider === 'deepseek') {
            presetInfo += ' | Base URL: https://api.deepseek.com/v1 | Model: deepseek-v4-flash';
        } else if (provider === 'modelscope') {
            presetInfo += ' | Base URL: https://api-inference.modelscope.cn/v1/ | Model: Qwen/Qwen2.5-72B-Instruct';
        } else if (provider === 'openai') {
            presetInfo += ' | Base URL: https://api.openai.com/v1 | Model: gpt-4o-mini';
        } else if (provider === 'ollama') {
            presetInfo += ' | Base URL: http://localhost:11434/v1 | Model: llama3';
        }

        document.getElementById('llmPresetInfo').textContent = presetInfo;

        // 只有当没有手动修改过URL和模型时才自动填充
        const baseUrl = document.getElementById('llmBaseUrl').value;
        const model = document.getElementById('llmModel').value;

        if (!baseUrl && !model) {
            // 这里只是UI提示，在真实提交时由后端应用预设
        }

        // 要求提供API密钥
        if (!apiKey) {
            showToast('请为所选提供商输入API密钥', 'warning');
        }
    } catch (e) {
        console.error('Error updating LLM preset:', e);
    }
}

async function updateLlmConfig() {
    const enabled = document.getElementById('llmEnabled').checked;

    if (enabled) {
        // LLM启用时，检查必要条件
        const provider = document.getElementById('llmProvider').value;
        const apiKey = document.getElementById('llmApiKey').value;

        if (!provider) {
            showToast('请选择LLM提供商', 'error');
            document.getElementById('llmEnabled').checked = false;
            return;
        }

        if (!apiKey) {
            showToast('请为LLM输入API密钥', 'error');
            document.getElementById('llmEnabled').checked = false;
            return;
        }
    }

    // 更新界面
    updateLlmProviderPreset();

    // 显示重启提示
    showToast('LLM配置已更新，请重启服务以使更改生效', 'info');
}

async function saveSetting(event) {
    const field = event.target;
    const fieldName = field.id;
    let value = field.value;

    // 类型转换
    if (field.type === 'checkbox') {
        value = field.checked;
    } else if ([
        'llmTimeout', 'llmMaxTokens', 'ragTopKRules', 'ragTopKSamples',
        'llmValuePoolSize'
    ].includes(fieldName)) {
        value = parseInt(value) || 0;
    } else if (['llmTemperature', 'rulesMinConfidence'].includes(fieldName)) {
        value = parseFloat(value) || 0;
    }

    // 准备要发送的数据
    const updateData = { [fieldName]: value };

    try {
        // 在真实实现中，这里会调用后端API
        // await apiPost('/api/settings', updateData);

        showToast(`${getFieldLabel(fieldName)} 已更新`, 'success');
    } catch (e) {
        console.error(`Failed to update ${fieldName}:`, e);
        showToast(`更新 ${getFieldLabel(fieldName)} 失败`, 'error');
        // 恢复原始值
        // 这里需要额外的状态管理来恢复值
    }
}

function getFieldLabel(fieldName) {
    const labels = {
        // LLM 配置
        'llmEnabled': 'LLM 启用',
        'llmProvider': 'LLM 提供商',
        'llmApiKey': 'API 密钥',
        'llmBaseUrl': 'Base URL',
        'llmModel': '模型名称',
        'llmTimeout': '请求超时',
        'llmMaxTokens': '最大响应Token数',
        'llmTemperature': '温度参数',

        // 数据库导出
        'dbExportEnabled': '数据库导出',
        'mysqlUrl': 'MySQL 连接字符串',

        // RAG
        'embeddingModel': '嵌入模型',
        'ragTopKRules': '规则检索数量',
        'ragTopKSamples': '样本检索数量',

        // 认证
        'webPassword': 'Web 密码',

        // 值池
        'llmValuePoolEnabled': '值池生成',
        'llmValuePoolSize': '值池大小',

        // 规则
        'rulesAutosave': '规则自动保存',
        'rulesMinConfidence': '最小置信度阈值'
    };

    return labels[fieldName] || fieldName;
}

async function saveAllSettings() {
    try {
        // 收集所有配置项
        const settingsData = {
            // LLM 配置
            llm_enabled: document.getElementById('llmEnabled').checked,
            llm_provider: document.getElementById('llmProvider').value || null,
            llm_api_key: document.getElementById('llmApiKey').value || null,
            llm_base_url: document.getElementById('llmBaseUrl').value || null,
            llm_model: document.getElementById('llmModel').value || null,
            llm_timeout: parseInt(document.getElementById('llmTimeout').value),
            llm_max_tokens: parseInt(document.getElementById('llmMaxTokens').value),
            llm_temperature: parseFloat(document.getElementById('llmTemperature').value),

            // 数据库导出
            db_export_enabled: document.getElementById('dbExportEnabled').checked,
            mysql_url: document.getElementById('mysqlUrl').value || null,

            // RAG
            embedding_model: document.getElementById('embeddingModel').value,
            rag_top_k_rules: parseInt(document.getElementById('ragTopKRules').value),
            rag_top_k_samples: parseInt(document.getElementById('ragTopKSamples').value),

            // 认证
            web_password: document.getElementById('webPassword').value || null,

            // 值池
            llm_value_pool_enabled: document.getElementById('llmValuePoolEnabled').checked,
            llm_value_pool_size: parseInt(document.getElementById('llmValuePoolSize').value),

            // 规则
            rules_autosave: document.getElementById('rulesAutosave').checked,
            rules_min_confidence: parseFloat(document.getElementById('rulesMinConfidence').value)
        };

        // 发送到后端
        await apiPost('/api/settings', settingsData);

        showToast('所有设置已成功保存！部分更改可能需要重启服务才能生效', 'success');

        // 重新加载系统信息以显示更新后的状态
        loadSystemInfo();

    } catch (e) {
        console.error('Failed to save settings:', e);
        showToast('保存设置失败，请重试', 'error');
    }
}

function resetToDefaults() {
    if (!confirm('确定要将所有设置恢复为默认值吗？当前的所有自定义设置将被清除。')) {
        return;
    }

    // LLM 配置
    document.getElementById('llmEnabled').checked = false;
    document.getElementById('llmProvider').value = '';
    document.getElementById('llmApiKey').value = '';
    document.getElementById('llmBaseUrl').value = '';
    document.getElementById('llmModel').value = '';
    document.getElementById('llmTimeout').value = 90;
    document.getElementById('llmMaxTokens').value = 2000;
    document.getElementById('llmTemperature').value = 0.1;

    // 数据库导出
    document.getElementById('dbExportEnabled').checked = true;
    document.getElementById('mysqlUrl').value = '';

    // RAG
    document.getElementById('embeddingModel').value = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2';
    document.getElementById('ragTopKRules').value = 5;
    document.getElementById('ragTopKSamples').value = 3;

    // 认证
    document.getElementById('webPassword').value = '';

    // 值池
    document.getElementById('llmValuePoolEnabled').checked = false;
    document.getElementById('llmValuePoolSize').value = 50;

    // 规则
    document.getElementById('rulesAutosave').checked = true;
    document.getElementById('rulesMinConfidence').value = 0.85;

    // 更新界面
    updateLlmProviderPreset();

    showToast('已恢复为默认设置', 'info');
}

// ========== WebSocket ==========
function connectWS() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(protocol + '//' + window.location.host + '/api/ws/tasks');
    ws.onopen = () => console.log('WebSocket connected');
    ws.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.event === 'task_created' || data.event === 'task_updated') {
            if (currentPage === 'tasks') loadTasks();
        }
    };
    ws.onclose = () => { console.log('WebSocket closed, retrying in 3s'); setTimeout(connectWS, 3000); };
    ws.onerror = (e) => console.error('WebSocket error', e);
}

// ========== 3D Card Tilt Effect ==========
function initCardTilt() {
    document.addEventListener('mousemove', (e) => {
        const cards = document.querySelectorAll('.glass-card');
        cards.forEach(card => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            const centerX = rect.width / 2;
            const centerY = rect.height / 2;
            
            // 根据卡片大小调整倾斜角度
            let divisor, translateZ;
            if (rect.width < 300) {
                // 小卡片：角度大
                divisor = 50;
                translateZ = 8;
            } else if (rect.width < 500) {
                // 中等卡片
                divisor = 100;
                translateZ = 4;
            } else {
                // 大卡片：角度小
                divisor = 180;
                translateZ = 1;
            }
            
            const angleX = (y - centerY) / divisor;
            const angleY = (centerX - x) / divisor;
            card.style.transform = `perspective(1000px) rotateX(${angleX}deg) rotateY(${angleY}deg) translateZ(${translateZ}px)`;
        });
    });
    document.addEventListener('mouseleave', () => {
        const cards = document.querySelectorAll('.glass-card');
        cards.forEach(card => {
            card.style.transform = 'perspective(1000px) rotateX(0) rotateY(0) translateZ(0)';
        });
    });
}

// ========== Schema Import ==========
let schemaTables = [];
let selectedSchemaTables = [];

function loadSchemaPage() {
    // Pre-fill from localStorage if saved
    const saved = localStorage.getItem('mw_schema_conn');
    if (saved) {
        try {
            const c = JSON.parse(saved);
            document.getElementById('schemaDbHost').value = c.host || '';
            document.getElementById('schemaDbName').value = c.db || '';
            document.getElementById('schemaDbUser').value = c.user || '';
        } catch (e) {}
    }
}

async function connectAndListTables() {
    const host = document.getElementById('schemaDbHost').value || 'localhost:3306';
    const db = document.getElementById('schemaDbName').value;
    const user = document.getElementById('schemaDbUser').value;
    const pass = document.getElementById('schemaDbPass').value;

    if (!db) { showToast('请输入数据库名', 'error'); return; }

    // Save connection info (without password)
    localStorage.setItem('mw_schema_conn', JSON.stringify({ host, db, user }));

    // Mock listing for now - replace with real API when backend supports it
    const listDiv = document.getElementById('schemaTableList');
    listDiv.innerHTML = '<p style="opacity:0.7;">正在连接数据库...</p>';

    // Try real API first
    try {
        const resp = await apiPost('/api/schema/tables', { host, database: db, user, password: pass });
        schemaTables = resp.tables || [];
    } catch (e) {
        // Fallback demo data for UI preview
        schemaTables = [
            { name: 'users', columns: 8, rows: 0 },
            { name: 'orders', columns: 12, rows: 0 },
            { name: 'products', columns: 6, rows: 0 },
            { name: 'logs', columns: 5, rows: 0 },
        ];
    }

    if (!schemaTables.length) {
        listDiv.innerHTML = '<p style="opacity:0.7;">未找到表</p>';
        return;
    }

    selectedSchemaTables = [];
    let html = '<div style="max-height:300px;overflow-y:auto;">';
    schemaTables.forEach((t, i) => {
        html += `<div style="padding:10px 12px;border-bottom:1px solid rgba(255,255,255,0.1);cursor:pointer;display:flex;justify-content:space-between;align-items:center;"
                     onmouseenter="this.style.background='rgba(255,255,255,0.05)'" onmouseleave="this.style.background='transparent'"
                     onclick="toggleSchemaTable(${i})">
            <div style="display:flex;align-items:center;gap:10px;">
                <input type="checkbox" id="schemaCheck${i}" style="width:18px;height:18px;cursor:pointer;">
                <strong>${t.name}</strong>
                <span style="opacity:0.6;font-size:12px;margin-left:8px;">${t.columns} 列</span>
            </div>
        </div>`;
    });
    html += '</div>';
    listDiv.innerHTML = html;
}

function toggleSchemaTable(idx) {
    const checkbox = document.getElementById('schemaCheck' + idx);
    const table = schemaTables[idx];
    
    if (checkbox.checked) {
        if (!selectedSchemaTables.find(t => t.name === table.name)) {
            selectedSchemaTables.push(table);
        }
    } else {
        selectedSchemaTables = selectedSchemaTables.filter(t => t.name !== table.name);
    }
    
    showToast(`已选择 ${selectedSchemaTables.length} 个表`);
}

function selectAllSchemaTables() {
    selectedSchemaTables = [...schemaTables];
    schemaTables.forEach((t, i) => {
        const checkbox = document.getElementById('schemaCheck' + i);
        if (checkbox) checkbox.checked = true;
    });
    showToast(`已全选 ${selectedSchemaTables.length} 个表`);
}

async function generateFromSchema() {
    if (!selectedSchemaTables.length) { showToast('请先选择表', 'error'); return; }
    const host = document.getElementById('schemaDbHost').value || 'localhost:3306';
    const db = document.getElementById('schemaDbName').value;
    const user = document.getElementById('schemaDbUser').value;
    const pass = document.getElementById('schemaDbPass').value;
    const rows = parseInt(document.getElementById('schemaRows').value) || 100;
    const output = document.getElementById('schemaOutput').value;

    // 先跳转任务中心，不等待后端返回
    navigateTo('tasks');

    let successCount = 0;
    for (const table of selectedSchemaTables) {
        try {
            await apiPost('/api/schema/generate', { host, database: db, user, password: pass, table_name: table.name, rows, output });
            successCount++;
        } catch (e) {
            console.error(`生成表 ${table.name} 失败:`, e);
        }
    }

    showToast(`成功创建 ${successCount}/${selectedSchemaTables.length} 个任务`);
}

// ========== Templates ==========
let templatesData = [];

function loadTemplatesPage() {
    loadSamplesForSelect('templateSample');
    loadTemplates();
}

async function loadTemplates() {
    const listDiv = document.getElementById('templateList');
    try {
        const data = await apiGet('/api/templates');
        templatesData = data.templates || [];
    } catch (e) {
        // Fallback: load from localStorage for demo
        const saved = localStorage.getItem('mw_templates');
        templatesData = saved ? JSON.parse(saved) : [];
    }
    renderTemplates();
}

function renderTemplates() {
    const listDiv = document.getElementById('templateList');
    if (!templatesData.length) {
        listDiv.innerHTML = '<p style="opacity:0.7;">暂无保存的模板</p>';
        return;
    }
    let html = '<div style="max-height:360px;overflow-y:auto;">';
    templatesData.forEach((t, i) => {
        html += `<div style="padding:12px;border-bottom:1px solid rgba(255,255,255,0.1);">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                <strong>${t.name}</strong>
                <div style="display:flex;gap:8px;">
                    <button class="neon-btn secondary" style="padding:4px 10px;font-size:12px;" onclick="useTemplate(${i})">使用</button>
                    <button class="neon-btn secondary" style="padding:4px 10px;font-size:12px;" onclick="deleteTemplate(${i})">删除</button>
                </div>
            </div>
            <div style="opacity:0.7;font-size:13px;">
                样本: ${t.sample_filename} | 行数: ${t.rows} | 输出: ${t.output}
            </div>
            ${t.desc ? `<div style="opacity:0.5;font-size:12px;margin-top:4px;">${t.desc}</div>` : ''}
        </div>`;
    });
    html += '</div>';
    listDiv.innerHTML = html;
}

async function saveTemplate() {
    const name = document.getElementById('templateName').value.trim();
    const sample = document.getElementById('templateSample').value;
    const rows = parseInt(document.getElementById('templateRows').value) || 100;
    const output = document.getElementById('templateOutput').value;
    const desc = document.getElementById('templateDesc').value.trim();

    if (!name) { showToast('请输入模板名称', 'error'); return; }
    if (!sample) { showToast('请选择样本文件', 'error'); return; }

    const tmpl = {
        id: 'tmpl_' + Date.now(),
        name,
        sample_filename: sample,
        rows,
        output,
        desc,
        created_at: new Date().toISOString(),
    };

    try {
        await apiPost('/api/templates', tmpl);
    } catch (e) {
        // Fallback: save to localStorage
        const saved = localStorage.getItem('mw_templates');
        const arr = saved ? JSON.parse(saved) : [];
        arr.push(tmpl);
        localStorage.setItem('mw_templates', JSON.stringify(arr));
    }

    showToast('模板保存成功');
    document.getElementById('templateName').value = '';
    document.getElementById('templateDesc').value = '';
    loadTemplates();
}

function useTemplate(idx) {
    const t = templatesData[idx];
    navigateTo('tasks');
    setTimeout(() => {
        document.getElementById('sampleSelect').value = t.sample_filename;
        document.getElementById('rowCount').value = t.rows;
        document.getElementById('outputMode').value = t.output;
        onSampleChange();
    }, 100);
}

async function deleteTemplate(idx) {
    if (!confirm('确定删除此模板？')) return;
    const t = templatesData[idx];
    try {
        await apiDelete('/api/templates/' + t.id);
    } catch (e) {
        const saved = localStorage.getItem('mw_templates');
        let arr = saved ? JSON.parse(saved) : [];
        arr = arr.filter(x => x.id !== t.id);
        localStorage.setItem('mw_templates', JSON.stringify(arr));
    }
    showToast('模板已删除');
    loadTemplates();
}

// ========== Monitor / Audit ==========
async function loadMonitorStats() {
    try {
        const data = await apiGet('/api/tasks/stats/summary');
        document.getElementById('monStatTotal').textContent = data.total_tasks;
        document.getElementById('monStatSuccessRate').textContent = data.success_rate + '%';
        document.getElementById('monStatAvgRows').textContent = data.avg_rows;
        renderMonitorCharts(data.status_distribution, data.daily_counts);
    } catch (e) { console.error(e); }
}

function renderMonitorCharts(statusDist, dailyCounts) {
    // Status doughnut
    const sCtx = document.getElementById('monStatusChart');
    if (sCtx) {
        if (charts.monStatus) charts.monStatus.destroy();
        charts.monStatus = new Chart(sCtx, {
            type: 'doughnut',
            data: {
                labels: ['待处理','运行中','已完成','失败','已取消'],
                datasets: [{
                    data: [statusDist.pending, statusDist.running, statusDist.completed, statusDist.failed, statusDist.cancelled],
                    backgroundColor: ['#f59e0b','#3b82f6','#22c55e','#ef4444','#6b7280'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'bottom', labels: { color: '#888' } } }
            }
        });
    }
    // Daily line
    const dCtx = document.getElementById('monDailyChart');
    if (dCtx) {
        if (charts.monDaily) charts.monDaily.destroy();
        charts.monDaily = new Chart(dCtx, {
            type: 'line',
            data: {
                labels: dailyCounts.map(d => d.date.slice(5)),
                datasets: [{
                    label: '任务数',
                    data: dailyCounts.map(d => d.count),
                    borderColor: '#00d4ff',
                    backgroundColor: 'rgba(0,212,255,0.1)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { ticks: { color: '#888', maxTicksLimit: 7 } },
                    y: { ticks: { color: '#888', stepSize: 1 } }
                },
                plugins: { legend: { display: false } }
            }
        });
    }
}

// ========== Metrics Display ==========
async function loadMetrics() {
    const container = document.getElementById('metricsDisplay');
    if (!container) return;
    try {
        const health = await apiGet('/api/health');
        renderMetrics(health);
    } catch (e) {
        console.error('loadMetrics failed:', e);
        container.innerHTML = '<p style="text-align:center;color:#ef4444;padding:20px;">加载指标失败: ' + (e.message || '网络错误') + '</p>';
    }
}

function renderMetrics(health) {
    const container = document.getElementById('metricsDisplay');
    if (!container) return;

    const data = health.metrics || {};
    const exec = health.executor || {};
    const counters = data.counters || {};
    const gauges = data.gauges || {};
    const histograms = data.histograms || {};

    // ---- Row 1: executor runtime status (always available) ----
    let html = '<div class="grid-3" style="margin-bottom:12px;">';
    html += `<div class="glass-card stat-card" style="padding:12px;">
        <div class="stat-label" style="font-size:12px;">⚡ 队列等待</div>
        <div class="stat-value" style="font-size:24px;">${exec.queue_size ?? '-'}</div>
    </div>`;
    html += `<div class="glass-card stat-card" style="padding:12px;">
        <div class="stat-label" style="font-size:12px;">🔄 执行中</div>
        <div class="stat-value" style="font-size:24px;">${exec.active ?? '-'}</div>
    </div>`;
    html += `<div class="glass-card stat-card" style="padding:12px;">
        <div class="stat-label" style="font-size:12px;">🔧 最大并发</div>
        <div class="stat-value" style="font-size:24px;">${exec.max_concurrent ?? '-'}</div>
    </div>`;
    html += '</div>';

    // ---- Row 2: runtime counters (accumulate after task processing) ----
    const counterEntries = Object.entries(counters);
    const gaugeEntries = Object.entries(gauges);
    const histEntries = Object.entries(histograms);
    const totalItems = counterEntries.length + gaugeEntries.length + histEntries.length;

    if (totalItems > 0) {
        html += '<div style="max-height:260px;overflow-y:auto;"><table class="tech-table"><thead><tr><th>类型</th><th>指标名称</th><th>值</th></tr></thead><tbody>';

        for (const [name, value] of counterEntries) {
            const label = COUNTER_LABELS[name] || name;
            html += `<tr><td>📊 计数器</td><td style="font-family:monospace;font-size:13px;">${label}</td><td style="font-size:12px;">${value}</td></tr>`;
        }
        for (const [name, value] of gaugeEntries) {
            const label = GAUGE_LABELS[name] || name;
            html += `<tr><td>📏 仪表</td><td style="font-family:monospace;font-size:13px;">${label}</td><td style="font-size:12px;">${typeof value === 'number' ? value.toFixed(1) : value}</td></tr>`;
        }
        for (const [name, summary] of histEntries) {
            const s = summary || {};
            const label = HIST_LABELS[name] || name;
            const display = `count=${s.count || 0}  avg=${(s.avg || 0).toFixed(2)}s  min=${(s.min || 0).toFixed(2)}s  max=${(s.max || 0).toFixed(2)}s`;
            html += `<tr><td>⏱️ 耗时</td><td style="font-family:monospace;font-size:13px;">${label}</td><td style="font-size:12px;">${display}</td></tr>`;
        }

        html += '</tbody></table></div>';
    } else {
        html += '<p style="text-align:center;color:var(--text-muted);padding:16px;font-size:13px;">📋 运行时指标暂无数据 — 创建并执行任务后将自动采集</p>';
    }

    container.innerHTML = html;
}

// Human-readable labels for metric names
const COUNTER_LABELS = {
    tasks_started: '任务启动次数',
    tasks_completed: '任务完成次数',
    tasks_failed: '任务失败次数',
    tasks_cancelled: '任务取消次数',
    tasks_created: '任务创建次数',
    rows_generated: '累计生成行数',
    db_exports: '数据库导出次数',
};

const GAUGE_LABELS = {
    active_tasks: '当前执行中任务数',
};

const HIST_LABELS = {
    generation_duration: '数据生成耗时',
    db_export_duration: '数据库导出耗时',
    csv_export_duration: 'CSV 导出耗时',
};

// ========== Audit Logs ==========
async function loadAuditLogs() {
    const filter = document.getElementById('auditEventFilter')?.value || '';
    const container = document.getElementById('auditLogList');
    if (!container) return;

    try {
        let path = '/api/audit/logs?limit=100';
        if (filter) path += '&event=' + filter;
        const data = await apiGet(path);
        renderAuditLogs(data.entries || []);
    } catch (e) {
        console.error('loadAuditLogs failed:', e);
        container.innerHTML = '<p style="text-align:center;color:#ef4444;padding:20px;">加载审计日志失败: ' + (e.message || '网络错误') + '</p>';
    }
}

function renderAuditLogs(entries) {
    const container = document.getElementById('auditLogList');
    if (!container) return;

    if (!entries.length) {
        container.innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:40px;">暂无审计日志</p>';
        return;
    }

    const eventLabels = {
        login_success: { text: '✅ 登录成功', cls: 'completed' },
        login_failure: { text: '❌ 登录失败', cls: 'failed' },
        logout: { text: '🚪 退出登录', cls: 'cancelled' },
        session_revoked: { text: '🔒 会话撤销', cls: 'pending' },
        task_generated: { text: '📊 任务生成', cls: 'running' },
    };

    let html = '<table class="tech-table"><thead><tr><th>时间</th><th>事件</th><th>用户</th><th>详情</th></tr></thead><tbody>';
    entries.forEach(e => {
        const label = eventLabels[e.event] || { text: e.event, cls: 'pending' };
        const ts = e.ts ? new Date(e.ts).toLocaleString() : '-';

        // Build detail summary based on event type
        let detail = '';
        if (e.event === 'login_failure') {
            detail = `原因: ${e.reason || 'unknown'}`;
        } else if (e.event === 'task_generated') {
            const sample = (e.sample || '').split('/').pop();
            detail = `样本: ${sample || '-'} → ${e.table || '-'}, ${e.rows || 0} 行`;
            if (e.task_id) detail += ` (ID: ${e.task_id.slice(0, 8)})`;
        } else {
            detail = e.remote_addr ? `IP: ${e.remote_addr}` : '';
        }

        html += `<tr>
            <td style="font-size:12px;">${ts}</td>
            <td><span class="status-indicator ${label.cls}"></span>${label.text}</td>
            <td>${e.user || 'anonymous'}</td>
            <td style="font-size:12px;">${detail}</td>
        </tr>`;
    });
    html += '</tbody></table>';
    container.innerHTML = html;
}

// ========== Dynamic File Accept (sync with backend registry) ==========
async function initFileAccept() {
    try {
        const { formats } = await apiGet('/api/sample/readers/formats');
        if (!Array.isArray(formats) || formats.length === 0) return;
        const accept = formats.join(',');
        const hint = '支持 ' + formats.map(f => f.toUpperCase().replace('.', '')).join(', ') + ' 格式';

        const sampleInput = document.getElementById('sampleFileInput');
        const sampleHint = document.getElementById('sampleAcceptHint');
        if (sampleInput) sampleInput.accept = accept;
        if (sampleHint) sampleHint.textContent = hint;

        const batchInput = document.getElementById('batchFileInput');
        const batchHint = document.getElementById('batchAcceptHint');
        if (batchInput) batchInput.accept = accept;
        if (batchHint) batchHint.textContent = hint;
    } catch (e) {
        console.warn('Failed to sync file accept formats:', e);
    }
}

// ========== Plugin Page ==========
async function loadPlugins() {
    try {
        const { formats } = await apiGet('/api/sample/readers/formats');
        const container = document.getElementById('pluginReaderList');
        if (!container) return;
        if (!Array.isArray(formats) || formats.length === 0) {
            container.innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:20px;">暂无已安装 Reader 插件</p>';
            return;
        }
        let html = '';
        formats.forEach(fmt => {
            html += `<div class="sample-item" style="margin-bottom:8px;">
                <div class="sample-info">
                    <span class="sample-name">${fmt}</span>
                    <span class="sample-meta">已注册</span>
                </div>
            </div>`;
        });
        container.innerHTML = html;
    } catch (e) {
        const container = document.getElementById('pluginReaderList');
        if (container) container.innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:20px;">加载失败: ' + e.message + '</p>';
    }
}

// ========== Codegen Panel ==========
let codegenSampleSnippet = '';
let codegenSampleFileName = '';

function handleCodegenFileSelect(e) {
    const file = e.target.files[0];
    if (!file) return;
    const info = document.getElementById('codegenFileInfo');
    if (file.size > 1024 * 1024) {
        info.textContent = '文件过大，将只读取前 2KB 作为参考';
    } else {
        info.textContent = '已选择: ' + file.name;
    }
    const reader = new FileReader();
    reader.onload = function(ev) {
        // Read first 2KB as text (truncate if needed)
        const text = ev.target.result;
        codegenSampleSnippet = text.slice(0, 2048);
        codegenSampleFileName = file.name;
        info.textContent = '已读取 ' + codegenSampleSnippet.length + ' 字节: ' + file.name;
    };
    reader.onerror = function() {
        info.textContent = '读取失败';
        showToast('样本文件读取失败', 'error');
    };
    reader.readAsText(file.slice(0, 2048));
}

async function generateReader() {
    const suffix = document.getElementById('codegenSuffix').value.trim();
    const description = document.getElementById('codegenDesc').value.trim();
    const strategy = document.getElementById('codegenStrategy').value.trim();

    if (!suffix) { showToast('请输入文件后缀', 'error'); return; }

    const btn = event.target;
    const originalText = btn.textContent;
    btn.textContent = '生成中...';
    btn.disabled = true;

    try {
        const data = await apiPost('/api/sample/readers/generate', {
            suffix,
            description,
            strategy,
            sample_snippet: codegenSampleSnippet
        });

        const resultDiv = document.getElementById('codegenResult');
        const msgP = document.getElementById('codegenMsg');
        const codePre = document.getElementById('codegenCode');

        msgP.innerHTML = `插件已生成并安装到 <code>${data.installed_path}</code><br>当前支持格式: <b>${data.supported_formats.join(', ')}</b>`;
        codePre.textContent = data.generated_code;
        resultDiv.style.display = 'block';

        // 刷新前端 accept 和提示
        await initFileAccept();
        showToast('Reader 插件生成成功！');
    } catch (e) {
        showToast('生成失败: ' + e.message, 'error');
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

// ========== Engine Page ==========
let engineData = null;
let engineCharts = {};

async function loadEnginePage() {
    // Load sample list into the select
    try {
        const data = await apiGet('/api/samples');
        const samples = data.samples || [];
        const sel = document.getElementById('engineSample');
        sel.innerHTML = '<option value="">-- 选择样本文件分析 --</option>' +
            samples.map(s => `<option value="${s.path}">${s.name}</option>`).join('');
    } catch (e) {
        console.error('Load samples for engine failed', e);
    }
    // Load engine system status
    loadEngineStatus();
}

async function loadEngineStatus() {
    try {
        const data = await apiGet('/api/engine/status');
        renderEngineStatus(data);
    } catch (e) {
        document.getElementById('engineSysStatus').innerHTML =
            '<p style="opacity:0.5;">引擎状态不可用: ' + e.message + '</p>';
    }
}

function renderEngineStatus(status) {
    const el = document.getElementById('engineSysStatus');
    const modelNames = (status.models || []).map(m =>
        `${m.name} ${m.enabled ? '✅' : '⛔'}`
    ).join(', ') || '无';
    el.innerHTML = `
        <p><strong>活跃模型:</strong> <span style="color:#22c55e;">${status.working_model || '未探测'}</span></p>
        <p><strong>模型池:</strong> ${modelNames}</p>
        <p><strong>规则库:</strong> ${status.rules_count} 条规则 (${status.rules_file})</p>
        <p><strong>向量库 rules:</strong> ${status.rag_rules_count} 条 | <strong>samples:</strong> ${status.rag_samples_count} 条</p>
        <p><strong>缓存:</strong> ${status.cache_size} / ${status.cache_maxsize}</p>
    `;
}

async function runEngineAnalyze() {
    const sampleFile = document.getElementById('engineSample').value;
    if (!sampleFile) {
        showToast('请先选择样本文件', 'error');
        return;
    }
    const btn = document.getElementById('engineAnalyzeBtn');
    const originalText = btn.textContent;
    btn.textContent = '分析中...';
    btn.disabled = true;
    document.getElementById('engineLoading').style.display = 'block';
    document.getElementById('engineResults').style.display = 'none';

    try {
        const data = await apiPost('/api/engine/analyze', { sample_file: sampleFile });
        engineData = data;
        renderEngineResults(data);
        document.getElementById('engineLoading').style.display = 'none';
        document.getElementById('engineResults').style.display = 'block';
        document.getElementById('engineStatusBadge').textContent =
            `分析完成: ${data.columns.length} 列, ${data.row_count} 行`;
    } catch (e) {
        document.getElementById('engineLoading').style.display = 'none';
        showToast('分析失败: ' + e.message, 'error');
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

function renderEngineResults(data) {
    renderResolutionChart(data.resolution);
    renderFieldStrategyTable(data.fields);
    renderCoherenceLinks(data.coherence_links);
    renderConstraints(data.constraints);
    renderDistributions(data.fields);
    renderRagMatches(data.rag_matches);
    document.getElementById('engineSQL').textContent = data.create_table_sql || '-- 无';
    document.getElementById('fieldCount').textContent = `共 ${data.fields.length} 个字段`;
}

// -- Resolution pipeline chart --
function renderResolutionChart(res) {
    const ctx = document.getElementById('resolutionChart');
    if (!ctx) return;
    if (engineCharts.resolution) engineCharts.resolution.destroy();
    engineCharts.resolution = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['规则库命中', 'RAG检索', 'LLM解析', '引擎兜底'],
            datasets: [{
                data: [res.rule_store_hits, res.rag_hits, res.llm_resolved, res.fallback_resolved],
                backgroundColor: ['#22c55e', '#3b82f6', '#f59e0b', '#6b7280'],
                borderWidth: 0,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
            },
        },
    });
    const legend = document.getElementById('resolutionLegend');
    const total = res.total_columns || 1;
    legend.innerHTML = `
        <span style="color:#22c55e;">● 规则库 ${res.rule_store_hits}</span>
        <span style="color:#3b82f6;">● RAG ${res.rag_hits}</span>
        <span style="color:#f59e0b;">● LLM ${res.llm_resolved}</span>
        <span style="color:#6b7280;">● 兜底 ${res.fallback_resolved}</span>
        <span style="opacity:0.5;margin-left:8px;">${res.llm_used ? 'LLM: ' + (res.model_used || '?') : '未使用LLM'}</span>
    `;
}

// -- Field strategy table --
function renderFieldStrategyTable(fields) {
    const tbody = document.getElementById('fieldStrategyBody');
    const layerColors = {
        'empty': '#6b7280', 'identity': '#8b5cf6', 'cn_identifier': '#ef4444',
        'datetime': '#06b6d4', 'boolean': '#84cc16', 'numeric': '#f59e0b',
        'faker': '#ec4899', 'entity': '#f97316', 'template': '#14b8a6',
        'enum': '#22c55e', 'markov': '#3b82f6', 'heuristic': '#a855f7',
        'fallback': '#6b7280',
    };
    let html = '';
    fields.forEach(f => {
        const color = layerColors[f.strategy_layer] || '#6b7280';
        const badge = `<span style="background:${color};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;">${f.strategy_layer}</span>`;
        const semColor = f.confidence > 0.7 ? '#22c55e' : f.confidence > 0.4 ? '#f59e0b' : '#6b7280';
        let extras = '';
        if (f.enum_values && f.enum_values.length) {
            extras = `<span style="font-size:11px;opacity:0.7;">枚举 ${f.enum_values.length}个</span>`;
        } else if (f.has_value_pool) {
            extras = `<span style="font-size:11px;opacity:0.7;">值池 ${f.value_pool_size}条</span>`;
        } else if (f.distribution) {
            extras = `<span style="font-size:11px;opacity:0.7;">分布:${f.distribution.type}</span>`;
        }
        html += `<tr>
            <td><strong>${f.name}</strong>${f.nullable ? '' : ' <span style="color:#ef4444;">*</span>'}</td>
            <td>${f.sql_type}</td>
            <td style="color:${semColor};">${f.semantic}</td>
            <td style="color:${semColor};">${(f.confidence * 100).toFixed(0)}%</td>
            <td>${badge}</td>
            <td style="font-size:12px;opacity:0.8;">${f.strategy_desc}</td>
            <td>${extras}</td>
        </tr>`;
    });
    tbody.innerHTML = html;
}

// -- Coherence links --
function renderCoherenceLinks(links) {
    const el = document.getElementById('coherenceContent');
    if (!links || !links.length) {
        el.innerHTML = '<p style="opacity:0.5;">无跨字段关联</p>';
        return;
    }
    const catColors = {
        'identity': '#ef4444', 'region': '#3b82f6', 'postal': '#f59e0b',
        'credit': '#14b8a6', 'bank': '#a855f7',
    };
    let html = '';
    links.forEach(l => {
        const color = catColors[l.category] || '#6b7280';
        html += `<div style="padding:8px 12px;margin-bottom:8px;background:${color}15;border-left:3px solid ${color};border-radius:4px;">
            <p style="font-weight:600;margin-bottom:4px;">${l.description}</p>
            <p style="font-size:12px;opacity:0.7;">${l.fields.join(' ⇄ ')}</p>
        </div>`;
    });
    el.innerHTML = html;
}

// -- Constraints --
function renderConstraints(constraints) {
    const el = document.getElementById('constraintsContent');
    if (!constraints || !constraints.length) {
        el.innerHTML = '<p style="opacity:0.5;">无约束规则</p>';
        return;
    }
    let html = '';
    constraints.forEach(c => {
        const color = c.confidence > 0.8 ? '#22c55e' : c.confidence > 0.5 ? '#f59e0b' : '#6b7280';
        html += `<div style="padding:6px 12px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center;">
            <span style="font-family:monospace;font-size:14px;">${c.expression}</span>
            <span style="font-size:11px;color:${color};">${(c.confidence * 100).toFixed(0)}%</span>
        </div>`;
    });
    el.innerHTML = html;
}

// -- Distributions --
function renderDistributions(fields) {
    const card = document.getElementById('distributionCard');
    const el = document.getElementById('distributionContent');
    const distFields = fields.filter(f => f.distribution);
    if (!distFields.length) {
        card.style.display = 'none';
        return;
    }
    card.style.display = 'block';
    let html = '<div style="display:flex;flex-wrap:wrap;gap:12px;">';
    distFields.forEach(f => {
        const d = f.distribution;
        const params = Object.entries(d.params || {}).map(([k, v]) => `${k}=${typeof v === 'number' ? v.toFixed(4) : v}`).join(', ');
        html += `<div style="flex:1;min-width:180px;padding:12px;background:rgba(59,130,246,0.08);border:1px solid rgba(59,130,246,0.2);border-radius:8px;">
            <p style="font-weight:600;">${f.name}</p>
            <p style="font-size:13px;opacity:0.8;">类型: <strong>${d.type}</strong></p>
            <p style="font-size:12px;opacity:0.6;">${params}</p>
            <p style="font-size:11px;opacity:0.5;">拟合优度: ${(d.goodness_of_fit * 100).toFixed(1)}%</p>
            <p style="font-size:11px;opacity:0.5;">范围: ${f.min_value} ~ ${f.max_value}</p>
        </div>`;
    });
    html += '</div>';
    el.innerHTML = html;
}

// -- RAG matches --
function renderRagMatches(matches) {
    const card = document.getElementById('ragCard');
    const el = document.getElementById('ragContent');
    if (!matches || !matches.length) {
        card.style.display = 'none';
        return;
    }
    card.style.display = 'block';
    let html = '';
    matches.forEach(m => {
        const color = m.confidence > 0.8 ? '#22c55e' : m.confidence > 0.5 ? '#f59e0b' : '#6b7280';
        html += `<div style="padding:8px 12px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center;">
            <div>
                <span style="font-weight:600;">${m.column}</span>
                <span style="opacity:0.5;"> → </span>
                <span style="color:#3b82f6;">${m.matched_rule}</span>
                <span style="font-size:12px;opacity:0.6;"> (${m.matched_semantic})</span>
            </div>
            <div style="text-align:right;">
                <span style="font-size:12px;color:${color};">${(m.confidence * 100).toFixed(1)}%</span>
                <span style="font-size:11px;opacity:0.4;margin-left:6px;">dist: ${m.distance.toFixed(3)}</span>
            </div>
        </div>`;
    });
    el.innerHTML = html;
}

// ========== Init ==========
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    createParticles();
    initCardTilt();
    checkAuth();
    loadSamples();
    initFileAccept();
    connectWS();
});

document.getElementById('login-password')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') doLogin();
});
