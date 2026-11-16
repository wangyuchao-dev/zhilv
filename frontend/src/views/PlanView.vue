<template>
  <main class="container plan-page">
    <!-- ================= HERO ================= -->
    <section class="hero fade-up">
      <div class="hero-left">
        <div class="eyebrow">RAG AGENT · 智能行程规划</div>
        <h1 class="h1 hero-title">
          说清楚<span class="gradient-text">你想怎么玩</span>，<br />剩下的交给它。
        </h1>
        <p class="hero-sub">
          填完这张表，系统会检索本地攻略库、拆解你的偏好，<br class="pc-only" />
          再排出一份能直接照着走的行程 —— 景点、餐饮、住宿、预算全给到。
        </p>

        <div class="hero-stats">
          <div class="stat">
            <b class="mono">{{ options.cities.length }}</b>
            <span>座城市攻略</span>
          </div>
          <div class="stat-div"></div>
          <div class="stat">
            <b class="mono">2</b>
            <span>级 Agent 编排</span>
          </div>
          <div class="stat-div"></div>
          <div class="stat">
            <b class="mono">RAG</b>
            <span>向量检索增强</span>
          </div>
        </div>
      </div>

      <!-- 右侧轨道图：纯装饰，象征「检索 → 汇聚 → 生成」 -->
      <div class="hero-visual" aria-hidden="true">
        <svg viewBox="0 0 420 420">
          <defs>
            <linearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stop-color="#4d7cfe" stop-opacity=".7" />
              <stop offset="100%" stop-color="#7b5cfa" stop-opacity=".1" />
            </linearGradient>
            <radialGradient id="coreGrad">
              <stop offset="0%" stop-color="#8fb4ff" />
              <stop offset="100%" stop-color="#4d7cfe" stop-opacity="0" />
            </radialGradient>
          </defs>

          <!-- 三层轨道 -->
          <circle cx="210" cy="210" r="72" fill="none" stroke="url(#ringGrad)" stroke-width="1" stroke-dasharray="3 7" />
          <circle cx="210" cy="210" r="124" fill="none" stroke="url(#ringGrad)" stroke-width="1" stroke-dasharray="2 9" opacity=".7" />
          <circle cx="210" cy="210" r="176" fill="none" stroke="url(#ringGrad)" stroke-width="1" stroke-dasharray="1 12" opacity=".45" />

          <!-- 核心光 -->
          <circle cx="210" cy="210" r="52" fill="url(#coreGrad)" opacity=".5" />
          <circle cx="210" cy="210" r="7" fill="#a8c4ff" />

          <!-- 轨道上的节点 -->
          <g class="orbit orbit-1">
            <circle cx="210" cy="138" r="4.5" fill="#7fe9ff" />
            <circle cx="210" cy="138" r="10" fill="#7fe9ff" opacity=".18" />
          </g>
          <g class="orbit orbit-2">
            <circle cx="334" cy="210" r="4" fill="#a78bfa" />
            <circle cx="334" cy="210" r="9" fill="#a78bfa" opacity=".18" />
          </g>
          <g class="orbit orbit-3">
            <circle cx="210" cy="386" r="3.6" fill="#ffd08f" />
            <circle cx="210" cy="386" r="8" fill="#ffd08f" opacity=".16" />
          </g>

          <!-- 汇聚线 -->
          <g stroke="#4d7cfe" stroke-width="0.8" opacity=".28">
            <line x1="210" y1="138" x2="210" y2="203" />
            <line x1="334" y1="210" x2="217" y2="210" />
            <line x1="210" y1="386" x2="210" y2="217" />
          </g>
        </svg>
      </div>
    </section>

    <div class="main-split">
      <aside class="chat-panel card card-edge fade-up d1">
        <header class="chat-head">
          <h3>一句话说需求</h3>
          <p>描述你的行程，我整理成字段，确认后自动填入右侧表单</p>
        </header>

        <div class="chat-body">
          <p v-if="!chatMsgs.length" class="chat-empty">
            例：我叫张三，三个人去成都，预算一万左右
          </p>
          <template v-for="(m, i) in chatMsgs" :key="i">
            <div v-if="m.type === 'fields'" class="fields-card">
              <div class="fc-row" v-for="(v, k) in m.fields" :key="k">
                <span class="fc-k">{{ labelOf(k) }}</span>
                <span class="fc-v">{{ fmtVal(k, v) }}</span>
              </div>
              <button v-if="!m.done" class="fc-ok" @click="confirmFields(m)">确认填入</button>
              <span v-else class="fc-done">已填入右侧表单</span>
            </div>
            <div v-else :class="['msg', m.role]">{{ m.content }}</div>
          </template>
          <div v-if="chatLoading" class="msg assistant typing">识别中…</div>
        </div>

        <div class="chat-input">
          <textarea v-model="chatText" rows="2" placeholder="说一句就行，回车发送"
                    @keydown.enter.exact.prevent="sendChat"></textarea>
          <button class="btn btn-primary btn-sm" :disabled="chatLoading || !chatText.trim()"
                  @click="sendChat">{{ chatLoading ? '识别中' : '发送' }}</button>
        </div>


      </aside>

      <div class="form-col">
    <!-- ================= 01 基础信息 ================= -->
    <section class="card card-edge form-card fade-up d1">
      <header class="card-head">
        <span class="num mono">01</span>
        <div>
          <h3>基础信息</h3>
          <p>年龄会影响行程强度，我们会据此调整节奏</p>
        </div>
      </header>

      <div class="grid grid-4">
        <div class="field">
          <label class="field-label">姓名<span class="req">*</span></label>
          <input v-model.trim="form.user_name" class="input" :class="{ err: errs.user_name }"
                 placeholder="怎么称呼你" maxlength="20" />
          <span v-if="errs.user_name" class="field-err">{{ errs.user_name }}</span>
        </div>

        <div class="field">
          <label class="field-label">年龄<span class="req">*</span></label>
          <input v-model.number="form.age" type="number" class="input" :class="{ err: errs.age }"
                 placeholder="19" min="6" max="80" />
          <span v-if="errs.age" class="field-err">{{ errs.age }}</span>
        </div>

        <div class="field">
          <label class="field-label">性别</label>
          <select v-model="form.gender" class="select">
            <option v-for="g in options.genders" :key="g" :value="g">{{ g }}</option>
          </select>
        </div>

        <div class="field">
          <label class="field-label">出发城市<span class="hint">选填</span></label>
          <input v-model.trim="form.departure_city" class="input" placeholder="例如 沈阳" maxlength="30" />
        </div>
      </div>
    </section>

    <!-- ================= 02 目的地与日期 ================= -->
    <section class="card card-edge form-card fade-up d2">
      <header class="card-head">
        <span class="num mono">02</span>
        <div>
          <h3>去哪儿、什么时候</h3>
          <p>天数按起止日期自动算，每个城市资料最多支持 5 天</p>
        </div>
      </header>

      <div class="grid grid-4">
        <div class="field">
          <label class="field-label">目的地<span class="req">*</span></label>
          <select v-model="form.destination" class="select">
            <option v-for="c in options.cities" :key="c" :value="c">{{ c }}</option>
          </select>
        </div>

        <div class="field">
          <label class="field-label">开始日期<span class="req">*</span></label>
          <input v-model="form.start_date" type="date" class="input" :class="{ err: errs.start_date }"
                 @change="syncDays" />
          <span v-if="errs.start_date" class="field-err">{{ errs.start_date }}</span>
        </div>

        <div class="field">
          <label class="field-label">结束日期<span class="req">*</span></label>
          <input v-model="form.end_date" type="date" class="input" :class="{ err: errs.end_date }"
                 @change="syncDays" />
          <span v-if="errs.end_date" class="field-err">{{ errs.end_date }}</span>
        </div>

        <div class="field">
          <label class="field-label">出行人数<span class="req">*</span>
            <span class="hint">整数</span>
          </label>
          <input v-model.number="form.travelers" type="number" class="input"
                 :class="{ err: errs.travelers }" min="1" max="20" step="1"
                 @input="checkTravelers" @blur="checkTravelers" />
          <span v-if="errs.travelers" class="field-err">{{ errs.travelers }}</span>
        </div>
      </div>

      <div class="days-bar">
        <div class="days-badge">
          <span class="mono">{{ form.days }}</span>
          <i>天</i>
        </div>
        <span class="muted" style="font-size: 12.5px">
          {{ form.days }} 天 {{ form.travelers }} 人 · 人均预算
          <b class="mono" style="color: var(--cyan)">¥{{ perPerson }}</b>
          <span v-if="form.days > 5" style="color: #ff9aad"> （最多支持 5 天，请缩短日期）</span>
        </span>
      </div>
    </section>

    <!-- ================= 03 偏好 ================= -->
    <section class="card card-edge form-card fade-up d3">
      <header class="card-head">
        <span class="num mono">03</span>
        <div>
          <h3>偏好设置</h3>
          <p>这些决定了行程的取舍 —— 想玩什么、住哪档、能花多少</p>
        </div>
      </header>

      <div class="grid grid-3">
        <div class="field">
          <label class="field-label">节奏偏好</label>
          <select v-model="form.pace" class="select">
            <option v-for="p in options.paces" :key="p" :value="p">{{ p }}</option>
          </select>
        </div>

        <div class="field">
          <label class="field-label">住宿偏好</label>
          <select v-model="form.hotel_level" class="select">
            <option v-for="h in options.hotel_levels" :key="h" :value="h">{{ h }}</option>
          </select>
        </div>

        <div class="field">
          <label class="field-label">总预算（元）<span class="req">*</span></label>
          <input v-model.number="form.budget" type="number" class="input" :class="{ err: errs.budget }"
                 min="300" step="100" />
          <span v-if="errs.budget" class="field-err">{{ errs.budget }}</span>
        </div>
      </div>

      <div class="field mt-24">
        <label class="field-label">
          旅行偏好<span class="req">*</span>
          <span class="hint">可多选，至少一个</span>
        </label>
        <div class="chips">
          <button v-for="s in options.travel_styles" :key="s" type="button"
                  class="chip" :class="{ on: form.travel_style.includes(s) }"
                  @click="toggle('travel_style', s)">{{ s }}</button>
        </div>
        <span v-if="errs.travel_style" class="field-err">{{ errs.travel_style }}</span>
      </div>

      <div class="field mt-24">
        <label class="field-label">
          饮食偏好<span class="hint">可多选，没有就留空</span>
        </label>
        <div class="chips">
          <button v-for="d in options.diets" :key="d" type="button"
                  class="chip" :class="{ on: form.diet.includes(d) }"
                  @click="toggle('diet', d)">{{ d }}</button>
        </div>
      </div>
    </section>

    <!-- ================= 04 额外要求 ================= -->
    <section class="card card-edge form-card fade-up d4">
      <header class="card-head">
        <span class="num mono">04</span>
        <div>
          <h3>额外要求</h3>
          <p>有什么必须满足的，写在这里</p>
        </div>
      </header>

      <div class="field">
        <textarea v-model="form.extra_request" class="textarea" maxlength="200"
                  placeholder="例如：希望住在地铁站附近，方便交通；带老人，不要爬太多台阶"></textarea>
        <div class="between" style="margin-top: 6px">
          <span class="tiny">写得越具体，排出来的行程越贴合</span>
          <span class="tiny mono">{{ form.extra_request.length }}/200</span>
        </div>
      </div>
    </section>

    <!-- ================= 错误 ================= -->
    <Transition name="fade">
      <div v-if="error" class="alert">
        <span>{{ error }}</span>
      </div>
    </Transition>

      </div>
    </div>

    <!-- ================= 底部操作栏 ================= -->
    <div class="action-bar">
      <div class="action-inner">
        <div class="action-info">
          <template v-if="loading">
            <span class="spinner"></span>
            <span class="step-text">{{ stepText }}…</span>
            <div class="mini-progress"><i :style="{ width: progressPct + '%' }"></i></div>
            <span class="tiny mono">{{ progress }}/4</span>
          </template>
          <template v-else>
            <span class="tiny">下一步：生成结构化行程，可保存到历史</span>
          </template>
        </div>

        <button class="btn btn-primary btn-lg" :disabled="loading" @click="submit">
          <span v-if="loading" class="spinner"></span>
          {{ loading ? '生成中…' : '开始规划' }}
          <span v-if="!loading" style="font-size: 16px">→</span>
        </button>
      </div>
    </div>
  </main>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'

const router = useRouter()

const options = reactive({
  cities: [], travel_styles: [], diets: [], paces: [], hotel_levels: [], genders: [],
})

const today = new Date()
const iso = (d) => d.toISOString().slice(0, 10)
const plusDays = (n) => {
  const d = new Date(today)
  d.setDate(d.getDate() + n)
  return iso(d)
}

const form = reactive({
  user_name: '',
  age: null,
  gender: '不透露',
  departure_city: '',
  destination: '大连',
  start_date: plusDays(1),
  end_date: plusDays(3),
  days: 3,
  travelers: 2,
  pace: '适中',
  hotel_level: '舒适型',
  budget: 3000,
  travel_style: [],
  diet: [],
  extra_request: '',
})

const errs = reactive({})
const error = ref('')
const loading = ref(false)

// 异步生成用：提交后拿 task_id，每 800ms 查一次进度
const taskId = ref('')
const stepText = ref('')

// 聊天侧：抽到的字段渲染成卡片，用户点「确认填入」才写进表单
const chatMsgs = ref([])
const chatText = ref('')
const chatLoading = ref(false)
const progress = ref(0)
let pollTimer = null

const progressPct = computed(() => Math.min(100, (progress.value / 4) * 100))

const perPerson = computed(() =>
  form.travelers ? Math.round(form.budget / form.travelers) : 0
)

// 起止日期变了，立刻重算天数并给字段级提示
function syncDays() {
  if (!form.start_date || !form.end_date) return
  const a = new Date(form.start_date)
  const b = new Date(form.end_date)
  const n = Math.round((b - a) / 86400000) + 1
  form.days = n > 0 ? n : 0

  if (form.days < 1) {
    errs.end_date = '结束日期不能早于开始日期'
  } else if (form.days > 5) {
    errs.end_date = '当前行程 ' + form.days + ' 天，最多支持 5 天，请缩短日期'
  } else {
    delete errs.end_date
  }
}

// v-model 变化时也同步（粘贴日期、程序化赋值不走 change 事件）
watch(() => [form.start_date, form.end_date], syncDays)

// 人数：非整数 / 越界在输入框下面直接给中文提示，不让它跑到后端变英文 422
function checkTravelers() {
  const v = form.travelers
  if (v === '' || v === null || v === undefined) {
    errs.travelers = '请填写出行人数'
    return
  }
  const num = Number(v)
  if (!Number.isInteger(num)) {
    errs.travelers = '出行人数必须填整数'
  } else if (num < 1 || num > 20) {
    errs.travelers = '出行人数需在 1–20 之间'
  } else {
    delete errs.travelers
  }
}

function toggle(key, val) {
  const list = form[key]
  const i = list.indexOf(val)
  if (i >= 0) list.splice(i, 1)
  else list.push(val)
}

function validate() {
  Object.keys(errs).forEach((k) => delete errs[k])

  if (!form.user_name || form.user_name.length < 2) errs.user_name = '名字至少 2 个字'
  if (!form.age || form.age < 6 || form.age > 80) errs.age = '年龄需在 6–80 之间'
  if (!form.start_date) errs.start_date = '请选择开始日期'
  if (!form.end_date) errs.end_date = '请选择结束日期'
  else if (form.start_date && form.end_date < form.start_date) errs.end_date = '结束不能早于开始'

  // 天数必须和日期一致，且不能超过 5 —— 以前 syncDays 没被调用，这里也没查，
  // 结果选 17 天仍然按初始的 3 天提交了
  syncDays()
  if (!form.days || form.days < 1) errs.end_date = '请检查起止日期'
  else if (form.days > 5) errs.end_date = '当前行程 ' + form.days + ' 天，最多支持 5 天'

  checkTravelers()

  if (!form.travel_style.length) errs.travel_style = '至少选一个偏好'
  if (!form.budget || form.budget < 300) errs.budget = '预算至少 300 元'

  return Object.keys(errs).length === 0
}

const FIELD_LABEL = {
  destination: '目的地',
  start_date: '出发日期',
  end_date: '返程日期',
  days: '天数',
  travelers: '人数',
  budget: '预算',
  travel_style: '风格偏好',
  pace: '节奏',
  hotel_level: '住宿档次',
}

const labelOf = (k) => FIELD_LABEL[k] || k

function fmtVal(k, v) {
  if (Array.isArray(v)) return v.join('、')
  if (k === 'budget') return '¥' + Number(v).toLocaleString()
  if (k === 'travelers') return v + ' 人'
  if (k === 'days') return v + ' 天'
  return v
}

// 把一句话发给后端抽槽位
async function sendChat() {
  const text = chatText.value.trim()
  if (!text || chatLoading.value) return

  chatMsgs.value.push({ role: 'user', content: text })
  chatText.value = ''
  chatLoading.value = true

  try {
    const history = chatMsgs.value
      .filter((m) => m.content)
      .slice(-8)
      .map((m) => ({ role: m.role, content: m.content }))

    const res = await api.extract({ message: text, history, draft: { ...form } })

    const got = Object.fromEntries(
      Object.entries(res.fields || {}).filter(([, v]) => v !== null && v !== undefined && v !== '')
    )

    if (Object.keys(got).length) {
      // 抽到字段就渲染成卡片，等用户确认，不直接写进表单
      chatMsgs.value.push({ role: 'assistant', type: 'fields', fields: got, done: false })
    } else {
      chatMsgs.value.push({ role: 'assistant', content: res.reply || '没识别到行程信息，换个说法试试。' })
    }
  } catch (e) {
    chatMsgs.value.push({ role: 'assistant', content: '识别失败：' + (e.message || '未知错误') })
  } finally {
    chatLoading.value = false
  }
}

// 用户点「确认填入」后才写表单，然后主动追问还缺什么
function confirmFields(m) {
  const { days, ...rest } = m.fields
  Object.assign(form, rest)

  if (days && form.start_date) {
    const d = new Date(form.start_date)
    d.setDate(d.getDate() + days - 1)
    form.end_date = d.toISOString().slice(0, 10)
  }
  if (form.start_date && form.end_date) syncDays()

  m.done = true

  // 看表单现状还缺哪些必填项，直接问
  const need = ['destination', 'start_date', 'end_date', 'travelers', 'budget', 'travel_style']
  const missing = need.filter((k) => {
    const v = form[k]
    return v === '' || v === null || v === undefined || (Array.isArray(v) && !v.length)
  })

  chatMsgs.value.push({
    role: 'assistant',
    content: missing.length
      ? '已经填进右侧表单了。还差「' + missing.map(labelOf).join('、') + '」，补充一下？'
      : '需要的都齐了，检查一下右侧表单，点「开始规划」就行。',
  })
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function goResult(payload, result) {
  sessionStorage.setItem('zhilv_result', JSON.stringify({ request: payload, result }))
  router.push('/result')
}

function startPolling(payload) {
  pollTimer = setInterval(async () => {
    try {
      const st = await api.task(taskId.value)
      stepText.value = st.step || '处理中'
      progress.value = st.progress || 0

      if (st.status === 'done' && st.result) {
        stopPolling()
        loading.value = false
        goResult(payload, st.result)
      } else if (st.status === 'failed') {
        stopPolling()
        loading.value = false
        error.value = st.error || '生成失败，请换个条件再试'
      }
    } catch (e) {
      // 404 说明任务过期了，别再轮询下去
      stopPolling()
      loading.value = false
      error.value = e.message || '任务已失效，请重新提交'
    }
  }, 800)
}

async function submit() {
  error.value = ''
  if (!validate()) {
    error.value = '有几项还没填对，检查一下标红的地方'
    return
  }

  loading.value = true
  progress.value = 0
  stepText.value = '正在提交'

  // 生成过程要十几秒，关掉页面时定时器得停，不然一直打接口
  window.onbeforeunload = (e) => {
    if (loading.value) {
      e.preventDefault()
      e.returnValue = ''
    }
  }

  try {
    const payload = {
      ...form,
      age: Number(form.age),
      days: form.days,
      travelers: Number(form.travelers),
      budget: Number(form.budget),
    }

    const ack = await api.generate(payload)

    // 命中缓存：后端直接把结果带回来了，不用轮询
    if (ack.status === 'done' && ack.result) {
      loading.value = false
      window.onbeforeunload = null
      goResult(payload, ack.result)
      return
    }

    // 正常情况：拿到 task_id 开始轮询
    taskId.value = ack.task_id
    stepText.value = ack.step || '排队中'
    startPolling(payload)
  } catch (e) {
    loading.value = false
    window.onbeforeunload = null
    error.value = e.message || '生成失败，请稍后再试'
  }
}

onUnmounted(() => {
  stopPolling()
  window.onbeforeunload = null
})

onMounted(async () => {
  try {
    Object.assign(options, await api.options())
  } catch (e) {
    error.value = '后端没连上，先确认服务有没有启动'
  }
})
</script>

<style scoped>
.plan-page { padding-top: 56px; padding-bottom: 160px; }

/* ---------- Hero ---------- */
.hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 400px;
  align-items: center;
  gap: 30px;
  padding-bottom: 52px;
}
.hero-title { margin-top: 18px; font-size: clamp(32px, 4.4vw, 52px); }
.hero-sub { margin-top: 18px; color: var(--dim); font-size: 15.5px; line-height: 1.85; max-width: 620px; }

.hero-stats { display: flex; align-items: center; gap: 26px; margin-top: 34px; }
.stat { display: flex; flex-direction: column; gap: 2px; }
.stat b { font-size: 26px; font-weight: 800; letter-spacing: -0.5px; color: var(--ink); line-height: 1.15; }
.stat span { font-size: 12.5px; color: var(--mute); }
.stat-div { width: 1px; height: 30px; background: var(--line); }

/* 右侧轨道图 */
.hero-visual {
  width: 400px;
  height: 400px;
  justify-self: end;
  opacity: 0.9;
  filter: drop-shadow(0 0 40px rgba(77, 124, 254, 0.18));
}
.hero-visual svg { width: 100%; height: 100%; overflow: visible; }

.orbit {
  transform-box: view-box;
  transform-origin: 210px 210px;
  animation: orbitSpin 26s linear infinite;
}
.orbit-2 { animation-duration: 34s; animation-direction: reverse; }
.orbit-3 { animation-duration: 44s; }

@keyframes orbitSpin {
  to { transform: rotate(360deg); }
}

/* ---------- 卡片 ---------- */
.form-card { padding: 26px 28px 28px; margin-bottom: 18px; }

.card-head { display: flex; gap: 14px; align-items: flex-start; margin-bottom: 24px; }
.num {
  flex: 0 0 auto;
  width: 34px; height: 34px;
  border-radius: 9px;
  display: grid; place-items: center;
  font-size: 13px; font-weight: 700;
  color: #9fb8ff;
  background: rgba(77, 124, 254, 0.12);
  border: 1px solid rgba(77, 124, 254, 0.32);
}
.card-head h3 { font-size: 17.5px; font-weight: 700; letter-spacing: -0.2px; }
.card-head p { font-size: 13px; color: var(--mute); margin-top: 3px; }

/* ---------- 栅格 ---------- */
.grid { display: grid; gap: 18px; }
.grid-2 { grid-template-columns: repeat(2, 1fr); }
.grid-3 { grid-template-columns: repeat(3, 1fr); }
.grid-4 { grid-template-columns: repeat(4, 1fr); }

/* ---------- 天数条 ---------- */
.days-bar {
  display: flex; align-items: center; gap: 16px;
  margin-top: 20px; padding-top: 18px;
  border-top: 1px solid var(--line);
}
.days-badge {
  display: flex; align-items: baseline; gap: 3px;
  padding: 6px 16px; border-radius: 99px;
  background: linear-gradient(135deg, rgba(77,124,254,.22), rgba(123,92,250,.22));
  border: 1px solid rgba(77,124,254,.5);
  box-shadow: 0 0 22px rgba(77,124,254,.2);
}
.days-badge span { font-size: 22px; font-weight: 800; color: #fff; }
.days-badge i { font-style: normal; font-size: 12.5px; color: #9fb8ff; }

/* ---------- 错误 ---------- */
.alert {
  margin-top: 16px; padding: 13px 18px;
  border-radius: 11px;
  background: rgba(255, 92, 122, 0.09);
  border: 1px solid rgba(255, 92, 122, 0.32);
  color: #ffb3c1; font-size: 13px;
}

/* ---------- 底部操作栏 ---------- */
.action-bar {
  position: fixed; left: 0; right: 0; bottom: 0; z-index: 40;
  backdrop-filter: blur(24px) saturate(160%);
  -webkit-backdrop-filter: blur(24px) saturate(160%);
  background: rgba(5, 7, 13, 0.82);
  border-top: 1px solid var(--line);
}
.action-inner {
  max-width: 1180px; margin: 0 auto; padding: 14px 28px;
  display: flex; align-items: center; justify-content: space-between; gap: 20px;
}
.main-split {
  display: grid;
  grid-template-columns: 336px minmax(0, 1fr);
  gap: 22px;
  align-items: start;
}

.chat-panel {
  position: sticky; top: 92px; padding: 18px;
  display: flex; flex-direction: column; gap: 12px;
  max-height: calc(100vh - 130px);
}
.chat-head h3 { font-size: 15px; font-weight: 700; color: #fff; }
.chat-head p { font-size: 11.5px; color: var(--mute); margin-top: 4px; line-height: 1.6; }

.chat-body {
  flex: 1; overflow-y: auto; min-height: 120px; max-height: 340px;
  display: flex; flex-direction: column; gap: 8px; padding-right: 4px;
}
.chat-empty { font-size: 12px; color: var(--mute); line-height: 1.7; }
.msg {
  font-size: 12.5px; line-height: 1.65; padding: 9px 11px;
  border-radius: 9px; max-width: 92%; white-space: pre-wrap;
}
.msg.user { align-self: flex-end; background: rgba(77, 124, 254, 0.16); color: #dbe4f7; border: 1px solid rgba(77, 124, 254, 0.28); }
.msg.assistant { align-self: flex-start; background: rgba(255, 255, 255, 0.045); color: var(--dim); border: 1px solid var(--line); }
.msg.typing { color: var(--mute); font-style: italic; }

.chat-input { display: flex; gap: 8px; align-items: flex-end; }
.chat-input textarea {
  flex: 1; min-height: 44px; max-height: 90px; resize: none;
  padding: 9px 11px; border-radius: 9px; font-size: 12.5px; line-height: 1.5;
  background: rgba(255, 255, 255, 0.04); border: 1px solid var(--line);
  color: var(--ink); font-family: inherit;
}
.chat-input textarea:focus { outline: none; border-color: rgba(77, 124, 254, 0.55); }
.chat-input textarea::placeholder { color: #7c869e; }

.fields-card {
  align-self: flex-start; width: 100%;
  padding: 12px 13px; border-radius: 10px;
  background: rgba(77, 124, 254, 0.07);
  border: 1px solid rgba(77, 124, 254, 0.22);
  display: flex; flex-direction: column; gap: 7px;
}
.fc-row { display: flex; align-items: baseline; gap: 10px; font-size: 12.5px; }
.fc-k { flex: 0 0 62px; color: var(--mute); }
.fc-v { color: var(--ink); font-weight: 700; }
.fc-ok {
  margin-top: 4px; padding: 9px 12px; border-radius: 8px;
  background: linear-gradient(135deg, #4d7cfe, #7b5cfa);
  color: #fff; font-size: 12.5px; font-weight: 700;
  border: none; cursor: pointer; width: 100%;
}
.fc-ok:hover { filter: brightness(1.1); }
.fc-done { margin-top: 2px; font-size: 11.5px; color: #6fcf97; }
.chat-tip { font-size: 11.5px; color: var(--mute); text-align: center; }

@media (max-width: 1120px) {
  .main-split { grid-template-columns: 1fr; }
  .chat-panel { position: static; max-height: none; }
}

.action-info { display: flex; align-items: center; gap: 10px; color: var(--dim); font-size: 13.5px; }

.step-text { color: #c8d2e6; }

.mini-progress {
  width: 150px; height: 4px; border-radius: 99px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
}
.mini-progress i {
  display: block; height: 100%; border-radius: 99px;
  background: linear-gradient(90deg, #4d7cfe, #7b5cfa);
  transition: width 0.4s ease;
  box-shadow: 0 0 12px rgba(77, 124, 254, 0.6);
}
.btn-lg { padding: 14px 34px; font-size: 15.5px; border-radius: 13px; }

.fade-enter-active, .fade-leave-active { transition: opacity 0.25s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

@media (max-width: 1000px) {
  .grid-4 { grid-template-columns: repeat(2, 1fr); }
  .grid-3 { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 680px) {
  .plan-page { padding-top: 34px; padding-bottom: 150px; }
  .form-card { padding: 20px 18px 22px; }
  .grid-4, .grid-3, .grid-2 { grid-template-columns: 1fr; }
  .hero-stats { gap: 18px; }
  .pc-only { display: none; }
  .action-inner { padding: 12px 18px; }
  .action-info { display: none; }
  .btn-lg { width: 100%; }
}
</style>
