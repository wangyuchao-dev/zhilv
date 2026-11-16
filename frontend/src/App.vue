<template>
  <div class="page">
    <div class="aurora aurora-1"></div>
    <div class="aurora aurora-2"></div>
    <div class="aurora aurora-3"></div>

    <header class="nav">
      <div class="container nav-inner">
        <RouterLink to="/" class="brand">
          <div class="brand-mark">知</div>
          <div class="brand-text">
            <b>知旅</b>
            <span>ZHILV · AI TRAVEL</span>
          </div>
        </RouterLink>

        <nav class="nav-links">
          <RouterLink to="/" class="nav-link" :class="{ active: route.path === '/' }">规划</RouterLink>
          <RouterLink to="/result" class="nav-link" :class="{ active: route.path === '/result' }">行程</RouterLink>
          <RouterLink to="/history" class="nav-link" :class="{ active: route.path === '/history' }">历史</RouterLink>
        </nav>

        <div class="nav-status">
          <span class="dot" :class="{ off: !online }"></span>
          {{ online ? '服务正常' : '服务离线' }}
        </div>
      </div>
    </header>

    <RouterView v-slot="{ Component }">
      <Transition name="page" mode="out-in">
        <component :is="Component" />
      </Transition>
    </RouterView>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from './api'

const route = useRoute()
const online = ref(false)

onMounted(async () => {
  try {
    const h = await api.health()
    online.value = h.status === 'ok'
  } catch (e) {
    online.value = false
  }
})
</script>

<style>
.page-enter-active,
.page-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}
.page-enter-from {
  opacity: 0;
  transform: translateY(10px);
}
.page-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
