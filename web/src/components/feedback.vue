<template>
  <div class="research-component">
    <div class="content-box hypothesis-box">
      <h2>假设反馈</h2>
      <div class="deduction">
        <div class="deduction-content" v-if="feedbackHypothesis">
          <div v-if="feedbackHypothesis.observations">
            <h3>观察</h3>
            <p>
              {{ feedbackHypothesis.observations }}
            </p>
          </div>
          <div v-if="feedbackHypothesis.hypothesis_evaluation">
            <h3>假设评估</h3>
            <p>
              {{ feedbackHypothesis.hypothesis_evaluation }}
            </p>
          </div>
          <div v-if="feedbackHypothesis.new_hypothesis">
            <h3>新假设</h3>
            <p>
              {{ feedbackHypothesis.new_hypothesis }}
            </p>
          </div>
          <div v-if="feedbackHypothesis.exception">
            <h3>异常</h3>
            <p>{{ feedbackHypothesis.exception }}</p>
          </div>
          <div>
            <h3>决策</h3>
            <p>
              {{ feedbackHypothesis.decision }}
            </p>
          </div>
          <div v-if="feedbackHypothesis.reason">
            <h3>原因</h3>
            <p>
              {{ feedbackHypothesis.reason }}
            </p>
          </div>
        </div>
        <div class="deduction-content" v-else>
          <p>
            由于前置步骤发生错误，未生成反馈。
          </p>
        </div>
      </div>
    </div>
    <div class="content-box returns-box">
      <h2>回报反馈</h2>
      <div class="deduction" style="margin-top: 0.5em">
        <div class="deduction-chart" v-if="feedbackCharts">
          <div class="chart-toolbar">
            <button class="chart-enlarge-btn" @click="openChartModal">
              放大
            </button>
          </div>
          <div v-if="!chartModalVisible" v-html="feedbackCharts.chart_html"></div>
        </div>
        <div class="deduction-chart" v-else>
          <p style="padding-left: 1.875em">
            由于前置步骤发生错误，未生成反馈。
          </p>
        </div>
      </div>
      <div class="config-section">
        <h2 style="margin-top: 1em">配置</h2>
        <div v-if="feedbackConfig && feedbackConfig.config">
          <markdownToHtml :markdown="feedbackConfig.config"></markdownToHtml>
        </div>
        <div v-else>
          <p style="padding-left: 1.875em">
            由于前置步骤发生错误，未生成反馈。
          </p>
        </div>
      </div>
    </div>
    <div class="chart-modal" v-if="chartModalVisible">
      <div class="chart-modal-content gradient-border">
        <div class="chart-modal-header">
          <h3>回报图表</h3>
          <button class="chart-modal-close" @click="closeChartModal">
            关闭
          </button>
        </div>
        <div class="chart-modal-body" v-if="feedbackCharts">
          <div v-html="feedbackCharts.chart_html"></div>
        </div>
      </div>
    </div>
  </div>
</template>
<script setup>
import { ref, watch, onMounted, defineProps, nextTick } from "vue";
import markdownToHtml from "../components/markdownToHtml.vue";
const props = defineProps({
  currentData: Object,
  updateEnd: Boolean,
});
const currentData = ref(props.currentData);
const updateEnd = ref(props.updateEnd);
const feedbackCharts = ref(currentData.value.feedbackCharts);
const feedbackConfig = ref(currentData.value.feedbackConfig);
const feedbackHypothesis = ref(currentData.value.feedbackHypothesis);
const chartModalVisible = ref(false);

const openChartModal = () => {
  chartModalVisible.value = true;
};

const closeChartModal = () => {
  chartModalVisible.value = false;
};

const executeScripts = () => {
  // 获取 HTML 中所有的 <script> 标签
  const scripts = document.querySelectorAll("script");
  scripts.forEach((script) => {
    const newScript = document.createElement("script");
    if (script.src) {
      newScript.src = script.src; // 如果有 src 属性，加载外部脚本
    } else {
      newScript.innerHTML = script.innerHTML; // 否则执行内联脚本
    }
    document.body.appendChild(newScript); // 将新脚本标签插入到 body 中
    document.body.removeChild(newScript); // 执行完毕后移除它
  });
};

watch(
  () => [props.currentData, props.updateEnd],
  (newValue, oldValue) => {
    currentData.value = newValue[0];
    updateEnd.value = newValue[1];
    feedbackCharts.value = currentData.value.feedbackCharts;
    feedbackConfig.value = currentData.value.feedbackConfig;
    feedbackHypothesis.value = currentData.value.feedbackHypothesis;
    if (feedbackCharts.value) {
      nextTick(() => {
        executeScripts();
      });
    }
  }
);

watch(
  () => chartModalVisible.value,
  () => {
    if (feedbackCharts.value) {
      nextTick(() => {
        executeScripts();
      });
    }
  }
);

onMounted(() => {
  // 执行嵌入的 JavaScript
  if (feedbackCharts.value) {
    nextTick(() => {
      executeScripts();
    });
  }
});
</script>

<style scoped lang="scss">
.research-component {
  height: 100%;
  display: flex;
  gap: 1.89em;
  .content-box {
    width: 54%;
    height: 100%;
    color: var(--text-color);
    overflow: auto;
    h2 {
      font-size: 1.26em;
      font-weight: 700;
      line-height: 200%;
      margin-bottom: 0.45em;
    }
    .deduction {
      border-radius: 11px;
      background: var(--bg-white);
      padding: 0.9em 0;
      box-sizing: border-box;
      overflow-y: hidden;
      .deduction-content {
        height: calc(100vh - 21.2em);
        padding: 0.9em 1.6875em 0;
        overflow: auto;
        &::-webkit-scrollbar-thumb {
          background-color: #fff;
        }
        &:hover {
          &::-webkit-scrollbar-thumb {
            background-color: #e4e7ff;
          }
        }
        h3 {
          font-size: 1.1475em;
          font-weight: 700;
          line-height: 200%;
          margin-bottom: 0.45em;
          margin-top: 0.9em;
          &:first-child {
            margin-top: 0;
          }
        }
        p {
          font-family: "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", sans-serif;
          font-size: 0.9em;
          line-height: 180%;
          margin-bottom: 0.9em;
        }
      }
      .deduction-chart {
        max-height: none;
        overflow: auto;
        position: relative;
        .chart-toolbar {
          display: flex;
          justify-content: flex-end;
          padding: 0 1.2em 0.6em;
        }
        .chart-enlarge-btn {
          border: none;
          cursor: pointer;
          font-size: 0.95em;
          font-weight: 600;
          color: #fff;
          padding: 0.5em 1em;
          border-radius: 999px;
          background: linear-gradient(90deg, #2667ff 0%, #9d41ff 100%);
          box-shadow: 0 6px 16px rgba(38, 103, 255, 0.2);
        }
        &::-webkit-scrollbar-thumb {
          background-color: #fff;
        }
        &:hover {
          &::-webkit-scrollbar-thumb {
            background-color: #e4e7ff;
          }
        }
      }
    }
  }
}

.hypothesis-box {
  width: 46%;
}

.returns-box {
  display: flex;
  flex-direction: column;
}

.returns-box .deduction {
  flex: 2;
  display: flex;
  flex-direction: column;
}

.returns-box .deduction-chart {
  flex: 1;
}

.returns-box .config-section {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.returns-box .config-section :deep(.markdown-body) {
  flex: 1;
  max-height: none;
}

.chart-modal {
  position: fixed;
  inset: 0;
  background: rgba(255, 255, 255, 0.4);
  backdrop-filter: blur(6px);
  z-index: 999999;
  display: flex;
  align-items: center;
  justify-content: center;
}

.chart-modal-content {
  width: min(92vw, 1200px);
  height: min(85vh, 900px);
  background: #fff;
  border-radius: 18px;
  padding: 1.6em 2em 2em;
  display: flex;
  flex-direction: column;
}

.chart-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1em;
  h3 {
    font-size: 1.2em;
    font-weight: 700;
    color: var(--text-color);
  }
}

.chart-modal-close {
  border: none;
  cursor: pointer;
  font-size: 0.95em;
  font-weight: 600;
  color: #fff;
  padding: 0.5em 1.1em;
  border-radius: 999px;
  background: #b0b7c3;
}

.chart-modal-body {
  flex: 1;
  overflow: auto;
  padding: 0 0.4em 0.4em;
}
</style>
