<template>
  <main class="container history-page">
    <!-- ================= 标题 ================= -->
    <section class="head fade-up">
      <div class="eyebrow">SAVED PLANS</div>
      <h1 class="h1" style="margin-top: 14px">我的行程档案</h1>
      <p class="muted" style="margin-top: 12px">
        每次生成后点保存的行程都在这里，随时可以翻回去看
      </p>
    </section>

    <!-- ================= 统计 ================= -->
    <div class="stat-row fade-up d1">
      <div class="stat-card card">
        <div class="stat-val mono">{{ stats.total }}</div>
        <div class="stat-label">份行程</div>
      </div>
      <div class="stat-card card">
        <div class="stat-val mono">{{ stats.cities }}</div>
        <div class="stat-label">座城市</div>
      </div>
      <div class="stat-card card">
        <div class="stat-val mono">{{ stats.avg_days || 0 }}</div>
        <div class="stat-label">平均天数</div>
      </div>
      <div class="stat-card card">
        <div class="stat-val mono">{{ stats.total_travelers }}</div>
        <div class="stat-label">累计出行人次</div>
      </div>
    </div>

    <!-- ================= 筛选 ================= -->
    <div class="filters fade-up d2">
      <div class="filter-input">
        <span class="filter-icon">🔍</span>
        <input v-model="keyword" class="input" style="padding-left: 38px"
               placeholder="搜姓名或行程摘要" @keyup.enter="load" />
      </div>

      <select v-model="city" class="select" style="width: 160px" @change="load">
        <option value="">全部城市</option>
        <option v-for="c in cities" :key="c" :value="c">{{ c }}</option>
      </select>

      <button class="btn btn-ghost btn-sm" @click="load" :disabled="loading">
        {{ loading ? '查询中…' : '刷新' }}
      </button>

      <RouterLink to="/" class="btn btn-primary btn-sm" style="margin-left: auto">
        + 新建行程
      </RouterLink>
    </div>

    <!-- ================= 列表 ================= -->
    <section class="fade-up d3">
      <!-- 空 -->
      <div v-if="!loading && !plans.length" class="empty card card-edge">
        <div style="font-size: 38px; margin-bottom: 14px; opacity: 0.5">🗂</div>
        <h3 class="h2">还没有保存的行程</h3>
        <p class="muted mt-8">生成一份行程后，点右上角「保存行程」就会出现在这里</p>
        <RouterLink to="/" class="btn btn-primary mt-24">去规划 →</RouterLink>
      </div>

      <!-- 骨架 -->
      <div v-if="loading" class="plan-list">
        <div v-for="i in 3" :key="i" class="skeleton" style="height: 108px; border-radius: 16px"></div>
      </div>

      <!-- 卡片网格 -->
      <div v-else class="plan-grid">
        <article v-for="p in plans" :key="p.id" class="plan-card card card-edge">
          <div class="pc-top">
            <div>
              <h3 class="city-name">{{ p.destination }}</h3>
              <div class="pc-id mono">trip_{{ p.id }} · {{ p.start_date }}</div>
            </div>
            <span class="city-days mono">{{ p.days }}天</span>
          </div>

          <p class="pc-summary">{{ p.summary || '（无摘要）' }}</p>

          <div class="pc-meta">
            <span class="tag">{{ p.user_name }}</span>
            <span class="tag">{{ p.travelers }} 人</span>
            <span class="tag">{{ p.hotel_level }}</span>
            <span v-for="s in (p.travel_style || []).slice(0, 2)" :key="s" class="tag tag-blue">{{ s }}</span>
          </div>

          <div class="pc-foot">
            <span class="pc-time mono">{{ fmtDate(p.created_at) }}</span>
            <div class="pc-actions">
              <button class="btn btn-primary btn-sm" @click="openDetail(p.id)">查看详情</button>
              <button class="btn btn-ghost btn-sm del" @click="remove(p.id)">删除</button>
            </div>
          </div>
        </article>
      </div>
    </section>

    <!-- ================= 详情模态 ================= -->
    <Teleport to="body">
      <Transition name="modal">
        <div v-if="detail" class="modal-mask" @click.self="detail = null">
          <div class="modal card card-edge">
            <header class="modal-head">
              <div>
                <div class="eyebrow">PLAN DETAIL</div>
                <h3 style="font-size: 22px; font-weight: 800; margin-top: 8px">
                  {{ detail.destination }} · {{ detail.days }} 天
                </h3>
                <p class="tiny" style="margin-top: 6px">
                  {{ detail.user_name }} · {{ detail.travelers }} 人 ·
                  {{ detail.start_date }} → {{ detail.end_date }}
                </p>
              </div>
              <button class="modal-close" @click="detail = null">✕</button>
            </header>

            <div class="modal-body">
              <p class="detail-summary">{{ detail.summary }}</p>

              <div class="detail-budget">
                <span class="tiny">总预算</span>
                <b class="mono">¥{{ (detail.plan?.budget?.total || 0).toLocaleString() }}</b>
                <span class="tiny">人均 ¥{{ (detail.plan?.budget?.per_person || 0).toLocaleString() }}</span>
              </div>

              <div class="detail-days">
                <div v-for="d in (detail.plan?.daily_plans || [])" :key="d.day" class="dd-item">
                  <div class="dd-head">
                    <span class="mono dd-day">D{{ d.day }}</span>
                    <b>{{ d.theme }}</b>
                    <span class="tiny">{{ d.date }}</span>
                  </div>
                  <div class="dd-body">
                    <span class="dd-slot">上午 · {{ d.morning?.spot }}</span>
                    <span class="dd-slot">下午 · {{ d.afternoon?.spot }}</span>
                    <span class="dd-slot">晚上 · {{ d.evening?.spot }}</span>
                  </div>
                </div>
              </div>
            </div>

            <footer class="modal-foot">
              <button class="btn btn-ghost btn-sm" @click="detail = null">关闭</button>
            </footer>
          </div>
        </div>
      </Transition>
    </Teleport>
  </main>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'

const router = useRouter()

const plans = ref([])
const stats = reactive({ total: 0, cities: 0, avg_days: 0, total_travelers: 0 })
const cities = ref([])
const keyword = ref('')
const city = ref('')
const loading = ref(false)
const detail = ref(null)

function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

async function load() {
  loading.value = true
  try {
    const params = {}
    if (keyword.value) params.keyword = keyword.value
    if (city.value) params.destination = city.value
    plans.value = await api.list(params)
    Object.assign(stats, await api.stats())
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function openDetail(id) {
  // 跳到结果页看完整版（支持刷新、可分享链接）
  router.push('/result?id=' + id)
}

async function remove(id) {
  if (!confirm('确定删除这条记录？删了就找不回来了')) return
  try {
    await api.remove(id)
    await load()
  } catch (e) {
    alert('删除失败：' + e.message)
  }
}

onMounted(async () => {
  try {
    const opt = await api.options()
    cities.value = opt.cities
  } catch (e) {
    /* 后端没起来也不影响列表 */
  }
  await load()
})
</script>

<style scoped>
.history-page { padding-top: 48px; padding-bottom: 90px; }
.head { margin-bottom: 34px; }

/* ---------- 统计 ---------- */
.stat-row {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px;
  margin-bottom: 26px;
}
.stat-card {
  padding: 20px 22px;
  display: flex; flex-direction: column; gap: 4px;
}
.stat-val { font-size: 30px; font-weight: 800; letter-spacing: -1px; line-height: 1.15; }
.stat-label { font-size: 12.5px; color: var(--mute); }

/* ---------- 筛选 ---------- */
.filters { display: flex; gap: 12px; align-items: center; margin-bottom: 20px; flex-wrap: wrap; }
.filter-input { position: relative; flex: 1; min-width: 200px; }
.filter-icon {
  position: absolute; left: 14px; top: 50%; transform: translateY(-50%);
  font-size: 13px; opacity: 0.6; pointer-events: none;
}

/* ---------- 列表 ---------- */
.plan-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.plan-card {
  display: flex; flex-direction: column;
  padding: 22px 22px 18px;
  min-height: 248px;
  transition: border-color 0.22s, background 0.22s, transform 0.22s, box-shadow 0.22s;
}
.plan-card:hover {
  border-color: rgba(77, 124, 254, 0.45);
  background: rgba(77, 124, 254, 0.035);
  transform: translateY(-3px);
  box-shadow: 0 14px 40px rgba(0, 0, 0, 0.45);
}

.pc-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
.city-name { font-size: 28px; font-weight: 800; letter-spacing: -0.8px; line-height: 1.15; color: #fff; }
.pc-id { font-size: 11.5px; color: var(--mute); margin-top: 5px; }
.city-days {
  flex: 0 0 auto;
  font-size: 12px; font-weight: 700; color: #9fb8ff;
  padding: 4px 10px; border-radius: 7px;
  background: rgba(77, 124, 254, 0.14);
  border: 1px solid rgba(77, 124, 254, 0.32);
}
.pc-summary {
  font-size: 13.5px; color: var(--dim); line-height: 1.72;
  margin: 14px 0 12px;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.pc-meta { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; }

.pc-foot {
  margin-top: auto;
  padding-top: 13px;
  border-top: 1px solid var(--line);
  display: flex; flex-direction: column; gap: 11px;
}
.pc-time { font-size: 11.5px; color: var(--mute); }
.pc-actions { display: flex; gap: 8px; }
.pc-actions .btn { flex: 1; padding: 9px 10px; font-size: 12.5px; }
.del:hover { color: #ffb3c1; border-color: rgba(255, 92, 122, 0.4); }

/* ---------- 空态 ---------- */
.empty { padding: 70px 30px; text-align: center; }

/* ---------- 模态 ---------- */
.modal-mask {
  position: fixed; inset: 0; z-index: 100;
  background: rgba(3, 5, 10, 0.78);
  backdrop-filter: blur(8px);
  display: grid; place-items: center;
  padding: 24px;
}
.modal {
  width: 100%; max-width: 720px; max-height: 84vh;
  display: flex; flex-direction: column;
  background: var(--elev);
}
.modal-head {
  display: flex; align-items: flex-start; justify-content: space-between;
  padding: 24px 26px 18px; border-bottom: 1px solid var(--line);
}
.modal-close {
  width: 32px; height: 32px; border-radius: 9px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--line);
  color: var(--dim); cursor: pointer; font-size: 14px;
  transition: all 0.2s;
}
.modal-close:hover { background: rgba(255, 255, 255, 0.1); color: var(--ink); }

.modal-body { padding: 22px 26px; overflow-y: auto; flex: 1; }
.detail-summary { font-size: 14px; color: #c8d2e6; line-height: 1.8; }

.detail-budget {
  display: flex; align-items: baseline; gap: 12px;
  margin-top: 18px; padding: 14px 18px; border-radius: 11px;
  background: rgba(77, 124, 254, 0.07);
  border: 1px solid rgba(77, 124, 254, 0.2);
}
.detail-budget b { font-size: 22px; color: #fff; }

.detail-days { display: flex; flex-direction: column; gap: 10px; margin-top: 20px; }
.dd-item {
  padding: 14px 16px; border-radius: 11px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--line);
}
.dd-head { display: flex; align-items: baseline; gap: 10px; }
.dd-day {
  font-size: 10.5px; font-weight: 700; color: var(--blue);
  padding: 2px 8px; border-radius: 5px;
  background: rgba(77, 124, 254, 0.12);
}
.dd-head b { font-size: 14.5px; }
.dd-body { display: flex; flex-wrap: wrap; gap: 8px 18px; margin-top: 9px; }
.dd-slot { font-size: 13px; color: var(--dim); }

.modal-foot {
  padding: 16px 26px; border-top: 1px solid var(--line);
  display: flex; justify-content: flex-end;
}

.modal-enter-active, .modal-leave-active { transition: opacity 0.25s; }
.modal-enter-from, .modal-leave-to { opacity: 0; }

@media (max-width: 1180px) {
  .plan-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 860px) {
  .stat-row { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 680px) {
  .history-page { padding-top: 30px; }
  .plan-grid { grid-template-columns: 1fr; }
  .plan-card { padding: 18px; min-height: auto; }
}
</style>
