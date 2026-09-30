<template>
  <div class="app">
    <aside class="side">
      <div class="brand">
        <img src="/app.png" alt="logo" class="logo" />
        <span class="brand-name">AI 课堂助手</span>
      </div>
      <nav>
        <button v-for="p in pages" :key="p.id" class="nav-btn"
                :class="{ active: page === p.id }" @click="page = p.id">
          {{ p.label }}
        </button>
      </nav>
      <div class="side-foot">
        <span class="dot" :class="phaseClass"></span>
        <span>{{ phaseText }}</span>
      </div>
    </aside>

    <main class="main">
      <!-- 总览 -->
      <section v-if="page === 'overview'" class="page">
        <h2 class="page-title">总览</h2>
        <div class="cards">
          <div class="card">
            <div class="card-label">当前课程</div>
            <div class="card-value">{{ state.current?.name || '—' }}</div>
            <div class="card-sub">{{ state.current ? `${state.current.subject} · ${state.current.lesson_type} · 已上 ${state.current.elapsed_min} 分钟` : '等待 ClassIsland 课程事件' }}</div>
          </div>
          <div class="card">
            <div class="card-label">文本模型</div>
            <div class="card-value">{{ state.server?.ollama_model || '未选择' }}</div>
            <div class="card-sub">视觉：{{ state.server?.ollama_vision || '—' }}</div>
          </div>
          <div class="card">
            <div class="card-label">监控</div>
            <div class="card-value">{{ monitor.recording ? '录制中' : state.server?.monitoring ? '运行中' : '已关闭' }}</div>
            <div class="card-sub">保留 14 天 · 按课程切片</div>
          </div>
          <div class="card">
            <div class="card-label">公网 IP</div>
            <div class="card-value">{{ state.server?.public_ip || '获取中…' }}</div>
            <div class="card-sub">OpenList：{{ remote.openlist_url || '未启动' }}</div>
          </div>
        </div>

        <h2 class="page-title" style="margin-top: 26px">课堂感知</h2>
        <div class="cards">
          <div class="card">
            <div class="card-label">麦克风分贝</div>
            <div class="card-value">{{ perception.mic_db ?? '—' }} <span class="unit">dB</span></div>
            <div class="card-sub">共享模式 · 不独占</div>
          </div>
          <div class="card">
            <div class="card-label">摄像头人脸</div>
            <div class="card-value">{{ perception.face_count ?? '—' }} <span class="unit">人</span></div>
            <div class="card-sub">基线：{{ perception.baseline ?? '—' }} · 共享模式</div>
          </div>
          <div class="card">
            <div class="card-label">屏幕活跃度</div>
            <div class="card-value">{{ screenPct }}<span class="unit">%</span></div>
            <div class="card-sub">拖堂判定主信号</div>
          </div>
          <div class="card">
            <div class="card-label">感知状态</div>
            <div class="card-value">{{ perception.active ? '采集中' : '待机' }}</div>
            <div class="card-sub">上课自动启动 · 下课自动停止</div>
          </div>
        </div>

        <h2 class="page-title" style="margin-top: 26px">今日课程</h2>
        <table class="tbl" v-if="state.today_lessons?.length">
          <thead><tr><th>时间</th><th>课程</th><th>科目</th><th>课型</th></tr></thead>
          <tbody>
            <tr v-for="(l, i) in state.today_lessons" :key="i">
              <td>{{ l.start }} – {{ l.end }}</td>
              <td>{{ l.name }}</td>
              <td>{{ l.subject }}</td>
              <td><span class="type-badge">{{ l.lesson_type }}</span></td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty">今日暂无已下课课程记录</p>
      </section>

      <!-- 课程 -->
      <section v-else-if="page === 'lessons'" class="page">
        <h2 class="page-title">课程</h2>
        <div class="card">
          <div class="card-label">ClassIsland 集成</div>
          <div class="card-value" style="font-size:16px">官方 IPC 订阅课程事件</div>
          <div class="card-sub">上课/下课/课间/放学事件由 ClassIsland 推送，本软件据此自动感知与产出。课表请在 ClassIsland 中维护。</div>
        </div>
        <div class="card" style="margin-top:16px">
          <div class="card-label">课型路由</div>
          <ul class="route-list">
            <li><b>新授课</b>：老师总结 + 学生总结 + 导学案 + 思维导图</li>
            <li><b>讲评课</b>：老师总结 + 学生总结 + 变式练习（不出思维导图）</li>
            <li><b>考试 / 自习</b>：仅老师总结（分贝折线 + 平均分贝）</li>
            <li><b>电影 / 无内容 / 电脑未开机</b>：不产出任何文件（监控录像除外）</li>
          </ul>
        </div>
      </section>

      <!-- 总结文件 -->
      <section v-else-if="page === 'summaries'" class="page">
        <h2 class="page-title">课堂总结 <button class="mini" @click="loadSummaries">刷新</button></h2>
        <div v-if="summaries.length" class="file-list">
          <div v-for="f in summaries" :key="f.path" class="file-item">
            <span class="file-name">{{ f.name }}</span>
            <span class="file-path">{{ f.path }}</span>
            <button class="mini" @click="openSummary(f.path)">打开</button>
          </div>
        </div>
        <p v-else class="empty">暂无总结文件（下课后自动生成，Markdown 格式）</p>
      </section>

      <!-- 设置 -->
      <section v-else class="page">
        <h2 class="page-title">设置</h2>

        <div class="card">
          <div class="card-label">Ollama 模型 <button class="mini" @click="refreshModels">刷新</button></div>
          <div class="card-label" style="margin-top:12px">文本模型（总结/导学案）</div>
          <select v-model="cfg.ollama.model" @change="saveCfg('ollama.model', cfg.ollama.model)">
            <option v-for="m in cfg.ollama.available_models" :key="m" :value="m">{{ m }}</option>
          </select>
          <div class="card-label" style="margin-top:12px">视觉模型（识图/座位表/板书）</div>
          <select v-model="cfg.ollama.vision_model" @change="saveCfg('ollama.vision_model', cfg.ollama.vision_model)">
            <option v-for="m in cfg.ollama.available_models" :key="m" :value="m">{{ m }}</option>
          </select>
        </div>

        <div class="card">
          <div class="card-label">感知与监控</div>
          <label class="row"><input type="checkbox" :checked="cfg.perception.mic_enabled" @change="saveCfg('perception.mic_enabled', $event.target.checked)" /> 麦克风感知（共享不独占）</label>
          <label class="row"><input type="checkbox" :checked="cfg.perception.cam_enabled" @change="saveCfg('perception.cam_enabled', $event.target.checked)" /> 摄像头感知（共享不独占）</label>
          <label class="row"><input type="checkbox" :checked="cfg.perception.screen_enabled" @change="saveCfg('perception.screen_enabled', $event.target.checked)" /> 屏幕感知（拖堂主信号）</label>
          <label class="row"><input type="checkbox" :checked="cfg.monitoring.enabled" @change="saveCfg('monitoring.enabled', $event.target.checked)" /> 监控默认开启（按课程切片，保留14天）</label>
          <div class="card-label" style="margin-top:10px">本地转写 ASR（faster-whisper，2核机器慎开）</div>
          <label class="row"><input type="checkbox" :checked="cfg.asr.enabled" @change="saveCfg('asr.enabled', $event.target.checked)" /> 启用上课语音转写</label>
        </div>

        <div class="card">
          <div class="card-label">座位表（图片上传，AI 识别姓名与换座）</div>
          <input type="file" accept="image/*" @change="uploadRoster" />
          <div class="card-sub" style="margin-top:8px">上传后由视觉模型解析座位布局；上课时自动检测换座并提示更新。</div>
        </div>

        <div class="card">
          <div class="card-label">远程访问（Cloudflare 隧道 + OpenList）</div>
          <div class="card-label" style="margin-top:10px">CF 隧道 Token</div>
          <input v-model="cfg.remote.tunnel_token" type="password" placeholder="粘贴 Cloudflare 隧道 token" style="width:100%" @change="saveCfg('remote.tunnel_token', $event.target.value)" />
          <div class="row" style="margin-top:12px">
            <button class="mini" @click="startRemote">启动远程</button>
            <button class="mini" @click="stopRemote">停止</button>
            <span class="card-sub">{{ remote.openlist_url ? `OpenList: ${remote.openlist_url}` : '' }}</span>
          </div>
          <div class="card-sub" style="margin-top:8px">工具（cloudflared / openlist）会自动下载到 tools/ 目录；下载失败时可手动放入。</div>
        </div>

        <div class="card">
          <div class="card-label">数据</div>
          <div class="row">
            <button class="mini" @click="exportAll">立即导出（监控+总结+座位表）</button>
            <button class="mini" @click="openExports">打开导出目录</button>
          </div>
          <div class="card-sub" style="margin-top:8px">导出到 data/exports，按 类型/日期/课程 分类；关机时自动导出。</div>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

const page = ref('overview')
const pages = [
  { id: 'overview', label: '总览' },
  { id: 'lessons', label: '课程' },
  { id: 'summaries', label: '总结文件' },
  { id: 'settings', label: '设置' },
]

const state = reactive({ phase: 'idle', current: null, today_lessons: [], server: {} })
const cfg = reactive({ ollama: { model: '', vision_model: '', available_models: [] }, perception: {}, monitoring: {}, asr: {}, remote: {} })
const perception = reactive({})
const remote = reactive({})
const monitor = reactive({})
const summaries = ref([])

const phaseText = computed(() =>
  state.phase === 'in_lesson' ? '上课中' : state.phase === 'processing' ? '生成总结中' : '待机')
const phaseClass = computed(() =>
  state.phase === 'in_lesson' ? 'ok' : state.phase === 'processing' ? 'busy' : 'idle')
const screenPct = computed(() =>
  perception.screen_active == null ? '—' : Math.round(perception.screen_active * 100))

async function api(path, options) {
  const resp = await fetch(path, options)
  return resp.json()
}

async function loadState() {
  Object.assign(state, await api('/api/state'))
}
async function loadConfig() {
  Object.assign(cfg, await api('/api/config'))
}
async function loadPerception() {
  Object.assign(perception, await api('/api/perception'))
}
async function loadRemote() {
  Object.assign(remote, await api('/api/remote/status'))
}
async function loadMonitor() {
  Object.assign(monitor, await api('/api/monitor/status'))
}
async function loadSummaries() {
  summaries.value = (await api('/api/summaries')).files || []
}

function saveCfg(key, value) {
  fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ [key]: value }),
  })
}
function refreshModels() {
  fetch('/api/models/refresh', { method: 'POST' })
  setTimeout(loadConfig, 2000)
}
function openSummary(path) {
  window.open(`/api/summary?path=${encodeURIComponent(path)}`, '_blank')
}
async function uploadRoster(ev) {
  const file = ev.target.files?.[0]
  if (!file) return
  const fd = new FormData()
  fd.append('file', file)
  await fetch('/api/roster', { method: 'POST', body: fd })
  alert('座位表已上传，正在后台解析…')
}
async function startRemote() {
  await fetch('/api/remote/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tunnel_token: cfg.remote.tunnel_token || '' }),
  })
  setTimeout(loadRemote, 2000)
}
async function stopRemote() {
  await fetch('/api/remote/stop', { method: 'POST' })
  setTimeout(loadRemote, 1000)
}
async function exportAll() {
  await fetch('/api/monitor/export', { method: 'POST' })
  alert('已导出到 data/exports')
}
function openExports() {
  window.open('http://127.0.0.1:5244', '_blank')
}

onMounted(async () => {
  await Promise.all([loadState(), loadConfig(), loadPerception(), loadRemote(), loadMonitor(), loadSummaries()])
  setInterval(loadState, 5000)
  setInterval(loadPerception, 5000)
  setInterval(loadMonitor, 10000)
})
</script>

<style scoped>
.app { display: flex; height: 100vh; background: #f4f7fc; }
.side { width: 220px; background: linear-gradient(180deg, #14203f 0%, #1e2f5e 100%); color: #fff; display: flex; flex-direction: column; padding: 22px 14px; }
.brand { display: flex; align-items: center; gap: 12px; margin-bottom: 30px; padding: 0 8px; }
.logo { width: 40px; height: 40px; border-radius: 10px; box-shadow: 0 4px 14px rgba(47,107,255,.35); }
.brand-name { font-size: 17px; font-weight: 700; letter-spacing: .5px; }
.nav-btn { display: block; width: 100%; text-align: left; padding: 11px 16px; margin-bottom: 8px; border: none; border-radius: 10px; background: transparent; color: #aab8dd; font-size: 14px; cursor: pointer; transition: all .18s; }
.nav-btn:hover { background: rgba(255,255,255,.07); color: #fff; }
.nav-btn.active { background: linear-gradient(90deg, #2f6bff, #4a84ff); color: #fff; box-shadow: 0 4px 14px rgba(47,107,255,.35); }
.side-foot { margin-top: auto; font-size: 13px; color: #8fa3cc; display: flex; align-items: center; gap: 8px; padding: 0 8px; }
.dot { width: 9px; height: 9px; border-radius: 50%; }
.dot.idle { background: #34c759; }
.dot.ok { background: #2f6bff; animation: pulse 1.2s infinite; }
.dot.busy { background: #ff9f0a; animation: blink 1s infinite; }
@keyframes blink { 50% { opacity: .3; } }
@keyframes pulse { 50% { box-shadow: 0 0 0 5px rgba(47,107,255,.2); } }
.main { flex: 1; padding: 30px 40px; overflow-y: auto; }
.page-title { font-size: 21px; margin-bottom: 16px; color: #14203f; display: flex; align-items: center; gap: 12px; font-weight: 700; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 16px; }
.card { background: #fff; border-radius: 16px; padding: 20px 22px; box-shadow: 0 2px 12px rgba(20,32,63,.06); border: 1px solid rgba(20,32,63,.04); }
.card-label { font-size: 13px; color: #6b7693; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
.card-value { font-size: 21px; font-weight: 700; color: #14203f; }
.unit { font-size: 13px; font-weight: 500; color: #8a94ad; }
.card-sub { font-size: 12px; color: #8a94ad; margin-top: 6px; }
.tbl { width: 100%; border-collapse: collapse; background: #fff; border-radius: 14px; overflow: hidden; box-shadow: 0 2px 12px rgba(20,32,63,.06); }
.tbl th, .tbl td { padding: 11px 16px; text-align: left; font-size: 14px; border-bottom: 1px solid #eef1f7; }
.tbl th { background: #f7f9fd; color: #6b7693; font-weight: 600; }
.type-badge { background: #eef4ff; color: #2f6bff; padding: 2px 10px; border-radius: 999px; font-size: 12px; }
.empty { color: #8a94ad; font-size: 14px; padding: 12px 0; }
.mini { font-size: 12px; padding: 4px 12px; border: 1px solid #d3dbe9; border-radius: 8px; background: #fff; cursor: pointer; transition: all .15s; }
.mini:hover { border-color: #2f6bff; color: #2f6bff; }
.file-list { background: #fff; border-radius: 14px; padding: 6px; box-shadow: 0 2px 12px rgba(20,32,63,.06); }
.file-item { display: flex; align-items: center; gap: 14px; padding: 11px 14px; border-bottom: 1px solid #eef1f7; }
.file-item:last-child { border-bottom: none; }
.file-name { font-weight: 600; font-size: 14px; color: #14203f; min-width: 220px; }
.file-path { flex: 1; font-size: 12px; color: #8a94ad; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
select, input[type="password"], input[type="file"] { padding: 8px 12px; border: 1px solid #d3dbe9; border-radius: 10px; font-size: 14px; width: 100%; box-sizing: border-box; }
.row { display: flex; align-items: center; gap: 10px; font-size: 14px; color: #14203f; margin-bottom: 10px; cursor: pointer; }
.route-list { padding-left: 18px; margin: 6px 0; font-size: 14px; line-height: 1.9; color: #33415e; }
</style>
