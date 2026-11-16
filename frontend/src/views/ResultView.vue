<template>
  <main class="container result-page">
    <!-- 没有数据 -->
    <div v-if="!data" class="empty card card-edge">
      <div class="empty-icon">✈</div>
      <h2 class="h2">还没有生成行程</h2>
      <p class="muted mt-8">先去填一张需求表，系统会排一份完整的行程给你</p>
      <RouterLink to="/" class="btn btn-primary mt-24">去规划 →</RouterLink>
    </div>

    <template v-else>
      <!-- ================= 顶部操作行 ================= -->
      <div class="top-bar fade-up">
        <div class="crumbs">
          <RouterLink to="/" class="crumb-link">← 返回修改</RouterLink>
          <span class="crumb-sep">/</span>
          <span class="tiny">{{ req.destination }} · {{ req.days }} 天 · {{ req.travelers }} 人</span>
        </div>

        <div class="top-actions">
          <span v-if="fromHistory" class="tag tag-blue">历史记录</span>
          <span v-else-if="result.cached" class="tag tag-cyan">缓存命中 · {{ (result.elapsed_ms / 1000).toFixed(1) }}s</span>
          <span v-else class="tag tag-blue">生成耗时 {{ (result.elapsed_ms / 1000).toFixed(1) }}s</span>

          <button class="btn btn-save" :disabled="saving || saved" @click="save">
            <span v-if="saving" class="spinner"></span>
            <span v-else-if="saved">✓</span>
            <span v-else>💾</span>
            {{ saving ? '保存中…' : saved ? '已保存' : '保存行程' }}
          </button>
        </div>
      </div>

      <!-- 保存成功提示 -->
      <Transition name="slide">
        <div v-if="savedMsg" class="saved-toast">
          <span class="dot"></span>
          {{ savedMsg }}
          <RouterLink to="/history" class="toast-link">去历史看看 →</RouterLink>
        </div>
      </Transition>

      <!-- ================= 概览 ================= -->
      <section class="card card-edge overview fade-up d1">
        <div class="ov-left">
          <div class="eyebrow">TRIP OVERVIEW</div>
          <h1 class="ov-title">
            {{ req.destination }}<span class="ov-days mono">{{ req.days }}天</span>
          </h1>
          <p class="ov-summary">{{ result.summary }}</p>

          <div class="ov-meta">
            <span class="tag">{{ req.start_date }} → {{ req.end_date }}</span>
            <span class="tag">{{ req.travelers }} 人</span>
            <span class="tag">{{ req.pace }}</span>
            <span class="tag">{{ req.hotel_level }}</span>
            <span v-for="s in req.travel_style" :key="s" class="tag tag-blue">{{ s }}</span>
          </div>

          <div v-if="(result.weather || []).length" class="ov-weather">
            <span class="wx-label">出行天气</span>
            <span v-for="w in result.weather" :key="w.date" class="wx-item">
              <b class="mono">{{ w.date.slice(5) }}</b>
              <span>{{ w.desc }}</span>
              <span class="mono">{{ w.tmin }}~{{ w.tmax }}℃</span>
              <span v-if="w.rain >= 40" class="wx-rain">降水 {{ w.rain }}%</span>
            </span>
          </div>
        </div>

        <div class="ov-right">
          <div class="budget-total">
            <div class="tiny">总预算（估算）</div>
            <div class="budget-num mono">
              ¥{{ result.budget.total.toLocaleString() }}
            </div>
            <div class="tiny">人均 ¥{{ result.budget.per_person.toLocaleString() }}</div>
          </div>
        </div>
      </section>

      <!-- ================= 亮点 + 预算 ================= -->
      <div class="two-col fade-up d2">
        <section class="card card-edge panel">
          <h3 class="panel-title">三个亮点</h3>
          <ul class="highlight-list">
            <li v-for="(h, i) in result.highlights" :key="i">
              <span class="hl-idx mono">{{ String(i + 1).padStart(2, '0') }}</span>
              <span>{{ h }}</span>
            </li>
          </ul>
        </section>

        <section class="card card-edge panel">
          <h3 class="panel-title">预算构成</h3>
          <div class="budget-rows">
            <div v-for="row in budgetRows" :key="row.key" class="b-row">
              <div class="b-label">{{ row.label }}</div>
              <div class="b-track">
                <div class="b-fill" :style="{ width: row.pct + '%', background: row.color }"></div>
              </div>
              <div class="b-val mono">¥{{ row.value }}</div>
            </div>
          </div>
        </section>
      </div>

      <!-- ================= 逐日行程 ================= -->
      <section class="fade-up d3" style="margin-top: 26px">
        <div class="between" style="margin-bottom: 14px">
          <h2 class="h2">完整行程</h2>
          <button class="btn btn-ghost btn-sm" @click="toggleAll">
            {{ allOpen ? '全部收起' : '全部展开' }}
          </button>
        </div>

        <div class="day-list">
          <article v-for="d in result.daily_plans" :key="d.day"
                   class="card card-edge day-card" :class="{ open: openDays[d.day] }">
            <!-- 头部 -->
            <header class="day-head" @click="toggleDay(d.day)">
              <div class="day-idx">
                <span class="mono">DAY {{ d.day }}</span>
              </div>
              <div class="day-title">
                <h4>{{ d.theme }}</h4>
                <span class="tiny mono">{{ d.date }}</span>
              </div>
              <div class="day-toggle">{{ openDays[d.day] ? '收起' : '展开' }}</div>
            </header>

            <!-- 展开内容 -->
            <div v-show="openDays[d.day]" class="day-body">
              <!-- 三个时段 -->
              <div class="slots">
                <div v-for="slot in slotsOf(d)" :key="slot.key" class="slot">
                  <div class="slot-time">
                    <span class="slot-icon">{{ slot.icon }}</span>
                    <span>{{ slot.label }}</span>
                  </div>
                  <div class="slot-main">
                    <div class="slot-spot">{{ slot.data.spot }}</div>
                    <div class="slot-activity">{{ slot.data.activity }}</div>
                    <div class="slot-meta">
                      <span class="mini-tag">⏱ {{ slot.data.duration }}</span>
                      <span class="mini-tag">🎫 {{ slot.data.ticket }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 餐饮住宿提示 -->
              <div class="day-extra">
                <div class="extra-item">
                  <span class="extra-label">餐饮</span>
                  <div>
                    <div>午餐 · {{ d.meals.lunch }}</div>
                    <div class="mt-8">晚餐 · {{ d.meals.dinner }}</div>
                  </div>
                </div>
                <div class="extra-item">
                  <span class="extra-label">住宿</span>
                  <div>{{ d.accommodation }}</div>
                </div>
                <div class="extra-item">
                  <span class="extra-label">提示</span>
                  <div>{{ d.tips }}</div>
                </div>
              </div>
            </div>
          </article>
        </div>
      </section>

      <!-- ================= 贴士 + 来源 ================= -->
      <div class="two-col fade-up d4" style="margin-top: 26px">
        <section class="card card-edge panel">
          <h3 class="panel-title">出行提示</h3>
          <ul class="tips-list">
            <li v-for="(t, i) in result.packing_tips" :key="i">{{ t }}</li>
          </ul>
        </section>

        <section class="card card-edge panel">
          <h3 class="panel-title">答案依据</h3>
          <p class="tiny" style="margin-bottom: 12px">
            以下片段来自本地攻略库，行程中的景点和价格都取自这里
          </p>
          <div class="source-list">
            <div v-for="(s, i) in result.sources" :key="i" class="source-item">
              <span class="src-idx mono">{{ String(i + 1).padStart(2, '0') }}</span>
              <div>
                <div class="src-title">{{ s.title }}</div>
                <div class="src-file mono">{{ s.source }}</div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </template>
  </main>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'

const route = useRoute()

const data = ref(null)
const req = ref({})
const result = ref({})

const openDays = reactive({})
const allOpen = ref(false)

const fromHistory = ref(false)
const saving = ref(false)
const saved = ref(false)
const savedMsg = ref('')

const BUDGET_META = [
  { key: 'transport', label: '交通', color: 'linear-gradient(90deg,#4d7cfe,#6b9bff)' },
  { key: 'hotel', label: '住宿', color: 'linear-gradient(90deg,#7b5cfa,#a78bfa)' },
  { key: 'food', label: '餐饮', color: 'linear-gradient(90deg,#00d9f5,#5eeaff)' },
  { key: 'ticket', label: '门票', color: 'linear-gradient(90deg,#ffb84d,#ffd08f)' },
  { key: 'other', label: '其他', color: 'linear-gradient(90deg,#3ddc97,#7ff0bb)' },
]

const budgetRows = computed(() => {
  const b = result.value.budget || {}
  const total = b.total || 1
  return BUDGET_META.map((m) => ({
    ...m,
    value: b[m.key] || 0,
    pct: Math.max(2, Math.round(((b[m.key] || 0) / total) * 100)),
  }))
})

function slotsOf(d) {
  return [
    { key: 'm', label: '上午', icon: '🌅', data: d.morning },
    { key: 'a', label: '下午', icon: '☀️', data: d.afternoon },
    { key: 'e', label: '晚上', icon: '🌙', data: d.evening },
  ]
}

function toggleDay(day) {
  openDays[day] = !openDays[day]
}

function toggleAll() {
  allOpen.value = !allOpen.value
  ;(result.value.daily_plans || []).forEach((d) => {
    openDays[d.day] = allOpen.value
  })
}

async function save() {
  if (saving.value || saved.value) return
  saving.value = true
  try {
    const plan = {
      summary: result.value.summary,
      highlights: result.value.highlights,
      budget: result.value.budget,
      daily_plans: result.value.daily_plans,
      packing_tips: result.value.packing_tips,
    }
    const res = await api.save({
      request: req.value,
      plan,
      sources: result.value.sources || [],
      // 带上生成时的 task_id，以后能反查这条记录是哪次生成的结果
      task_id: result.value.task_id || '',
      weather: result.value.weather || [],
    })
    saved.value = true
    savedMsg.value = `已保存到历史（记录 #${res.id}）`
    setTimeout(() => (savedMsg.value = ''), 6000)
  } catch (e) {
    savedMsg.value = '保存失败：' + e.message
    setTimeout(() => (savedMsg.value = ''), 6000)
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  // ① 从 URL 带 id 进来（历史页点「查看」），直接读库
  const id = route.query.id
  if (id) {
    try {
      const d = await api.detail(id)
      req.value = {
        user_name: d.user_name,
        age: d.age,
        gender: d.gender,
        departure_city: d.departure_city,
        destination: d.destination,
        start_date: d.start_date,
        end_date: d.end_date,
        days: d.days,
        travelers: d.travelers,
        pace: d.pace,
        hotel_level: d.hotel_level,
        budget: d.budget,
        travel_style: d.travel_style || [],
        diet: d.diet || [],
        extra_request: d.extra_request,
      }
      const plan = d.plan || {}
      result.value = {
        summary: d.summary,
        highlights: plan.highlights || [],
        budget: plan.budget || {},
        daily_plans: plan.daily_plans || [],
        packing_tips: plan.packing_tips || [],
        sources: d.sources || [],
        weather: plan.weather || [],
        cached: false,
        elapsed_ms: 0,
      }
      data.value = { request: req.value, result: result.value }
      fromHistory.value = true
      saved.value = true // 从库里读出来的，本来就是已保存状态
      if (result.value.daily_plans.length) {
        openDays[result.value.daily_plans[0].day] = true
      }
      return
    } catch (e) {
      console.error('加载历史详情失败', e)
    }
  }

  // ② 否则读刚生成的结果
  const raw = sessionStorage.getItem('zhilv_result')
  if (!raw) return
  try {
    const parsed = JSON.parse(raw)
    req.value = parsed.request
    result.value = parsed.result
    data.value = parsed

    // 默认展开第一天
    if (result.value.daily_plans?.length) {
      openDays[result.value.daily_plans[0].day] = true
    }
  } catch (e) {
    console.error(e)
  }
})
</script>

<style scoped>
.result-page { padding-top: 34px; padding-bottom: 90px; }

/* ---------- 空状态 ---------- */
.empty { padding: 80px 30px; text-align: center; }
.empty-icon { font-size: 42px; margin-bottom: 18px; opacity: 0.6; }

/* ---------- 顶部操作 ---------- */
.top-bar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 16px; margin-bottom: 20px; flex-wrap: wrap;
}
.crumbs { display: flex; align-items: center; gap: 10px; }
.crumb-link { color: var(--dim); text-decoration: none; font-size: 14px; transition: color 0.2s; }
.crumb-link:hover { color: var(--blue); }
.crumb-sep { color: var(--mute); }
.top-actions { display: flex; align-items: center; gap: 12px; }

.saved-toast {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 18px; margin-bottom: 18px;
  border-radius: 11px;
  background: rgba(61, 220, 151, 0.1);
  border: 1px solid rgba(61, 220, 151, 0.3);
  color: #8ff0c4; font-size: 13px;
}
.toast-link { color: #8ff0c4; text-decoration: underline; margin-left: 4px; }
.slide-enter-active, .slide-leave-active { transition: all 0.3s; }
.slide-enter-from, .slide-leave-to { opacity: 0; transform: translateY(-8px); }

/* ---------- 概览 ---------- */
.overview {
  display: flex; justify-content: space-between; align-items: center;
  gap: 30px; padding: 30px 32px;
}
.ov-title { font-size: clamp(28px, 3.6vw, 40px); font-weight: 800; letter-spacing: -1px; margin-top: 12px; }
.ov-days {
  font-size: 16px; font-weight: 700; margin-left: 12px;
  padding: 4px 12px; border-radius: 8px;
  background: rgba(77, 124, 254, 0.16);
  border: 1px solid rgba(77, 124, 254, 0.4);
  color: #9fb8ff; vertical-align: middle;
}
.ov-summary { color: var(--dim); margin-top: 12px; font-size: 15px; max-width: 560px; line-height: 1.8; }
.ov-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }

.ov-weather {
  display: flex; flex-wrap: wrap; align-items: center; gap: 9px;
  margin-top: 14px; padding-top: 13px;
  border-top: 1px dashed var(--line);
}
.wx-label { font-size: 12px; color: var(--mute); }
.wx-item {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 10px; border-radius: 7px;
  background: rgba(77, 124, 254, 0.09);
  border: 1px solid rgba(77, 124, 254, 0.2);
  font-size: 12.5px; color: var(--dim);
}
.wx-item b { color: var(--ink); font-weight: 700; }
.wx-rain { color: #7ec8ff; }

.ov-right { flex: 0 0 auto; text-align: right; }
.budget-total {
  padding: 18px 24px; border-radius: 14px;
  background: linear-gradient(135deg, rgba(77, 124, 254, 0.12), rgba(123, 92, 250, 0.08));
  border: 1px solid rgba(77, 124, 254, 0.28);
}
.budget-num { font-size: 34px; font-weight: 800; letter-spacing: -1px; color: #fff; margin: 4px 0; }

/* ---------- 双列 ---------- */
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-top: 18px; align-items: start; }
.panel { padding: 24px 26px; }
.panel-title { font-size: 15.5px; font-weight: 700; margin-bottom: 18px; letter-spacing: 0.3px; color: #fff; }

/* ---------- 亮点 ---------- */
.highlight-list { list-style: none; display: flex; flex-direction: column; gap: 14px; }
.highlight-list li { display: flex; gap: 12px; font-size: 14.5px; color: #c8d2e6; line-height: 1.6; }
.hl-idx { color: var(--blue); font-size: 12px; font-weight: 700; flex: 0 0 auto; padding-top: 3px; }

/* ---------- 预算 ---------- */
.budget-rows { display: flex; flex-direction: column; gap: 13px; }
.b-row { display: grid; grid-template-columns: 48px 1fr 72px; align-items: center; gap: 12px; }
.b-label { font-size: 13.5px; color: var(--dim); }
.b-track { height: 7px; border-radius: 99px; background: rgba(255, 255, 255, 0.06); overflow: hidden; }
.b-fill { height: 100%; border-radius: 99px; transition: width 0.9s cubic-bezier(0.16, 1, 0.3, 1); }
.b-val { font-size: 13px; color: #c8d2e6; text-align: right; }

/* ---------- 逐日 ---------- */
.day-list { display: flex; flex-direction: column; gap: 12px; }

.day-card { overflow: hidden; transition: border-color 0.25s; }
.day-card.open { border-color: rgba(77, 124, 254, 0.4); }

.day-head {
  display: flex; align-items: center; gap: 16px;
  padding: 18px 24px; cursor: pointer; user-select: none;
  transition: background 0.2s;
}
.day-head:hover { background: rgba(255, 255, 255, 0.025); }

.day-idx span {
  font-size: 11.5px; font-weight: 700; letter-spacing: 1.4px;
  color: var(--blue);
  padding: 4px 10px; border-radius: 6px;
  background: rgba(77, 124, 254, 0.12);
  border: 1px solid rgba(77, 124, 254, 0.3);
}
.day-title { flex: 1; display: flex; align-items: baseline; gap: 12px; }
.day-title h4 { font-size: 17px; font-weight: 700; color: #fff; }
.day-toggle { font-size: 13px; color: var(--mute); }

.day-body { padding: 0 24px 22px; border-top: 1px solid var(--line); }

/* ---------- 时段 ---------- */
.slots { display: flex; flex-direction: column; gap: 2px; padding: 18px 0; }

.slot {
  display: flex; gap: 16px; padding: 14px 0;
  border-bottom: 1px dashed rgba(255, 255, 255, 0.06);
}
.slot:last-child { border-bottom: none; }
.slot-time {
  flex: 0 0 76px; display: flex; align-items: center; gap: 7px;
  font-size: 14px; color: var(--dim); padding-top: 2px;
}
.slot-icon { font-size: 14px; }
.slot-main { flex: 1; }
.slot-spot { font-size: 16px; font-weight: 700; color: #fff; }
.slot-activity { font-size: 14.5px; color: #a8b3c8; margin-top: 5px; line-height: 1.65; }
.slot-meta { display: flex; gap: 8px; margin-top: 9px; }
.mini-tag {
  font-size: 12.5px; color: var(--mute);
  padding: 2px 9px; border-radius: 5px;
  background: rgba(255, 255, 255, 0.045);
  border: 1px solid var(--line);
}

/* ---------- 附加信息 ---------- */
.day-extra {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px;
  padding-top: 18px; border-top: 1px solid var(--line);
}
.extra-item { display: flex; gap: 10px; font-size: 13.5px; color: #a8b3c8; line-height: 1.65; }
.extra-label {
  flex: 0 0 auto; font-size: 12px; color: var(--mute);
  padding: 2px 8px; border-radius: 5px;
  background: rgba(255, 255, 255, 0.045);
  height: fit-content;
}

/* ---------- 贴士 ---------- */
.tips-list { list-style: none; display: flex; flex-direction: column; gap: 11px; }
.tips-list li {
  font-size: 14px; color: #a8b3c8; line-height: 1.7;
  padding-left: 16px; position: relative;
}
.tips-list li::before {
  content: ""; position: absolute; left: 0; top: 9px;
  width: 5px; height: 5px; border-radius: 50%;
  background: var(--blue);
}

/* ---------- 来源 ---------- */
.source-list { display: flex; flex-direction: column; gap: 10px; }
.source-item { display: flex; gap: 11px; align-items: flex-start; }
.src-idx { font-size: 11px; color: var(--mute); padding-top: 2px; }
.src-title { font-size: 13.5px; color: #c8d2e6; }
.src-file { font-size: 11.5px; color: var(--mute); margin-top: 2px; }

@media (max-width: 900px) {
  .two-col { grid-template-columns: 1fr; }
  .overview { flex-direction: column; align-items: flex-start; }
  .ov-right { text-align: left; width: 100%; }
  .budget-total { display: inline-block; }
  .day-extra { grid-template-columns: 1fr; }
}
@media (max-width: 680px) {
  .result-page { padding-top: 20px; }
  .top-bar { align-items: flex-start; }
  .overview { padding: 22px 18px; }
  .panel { padding: 20px 18px; }
  .day-head { padding: 15px 16px; }
  .day-body { padding: 0 16px 18px; }
  .slot-time { flex-basis: 64px; }
}
</style>
