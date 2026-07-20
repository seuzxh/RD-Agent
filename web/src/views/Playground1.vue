<template>
  <div class="main-content">
    <div class="step">
      <Step :activeIndex="0" />
    </div>
    <div class="intro">
      <h2>欢迎使用智能模型分析平台。</h2>
      <p>
        初次使用？选择场景并输入信息或上传文件。回访用户？上传您的代码文件以继续。
      </p>
    </div>
    <div class="content">
      <div class="scenario-item">
        <div class="scenario-item-text">
          <p class="p1">
            <SvgIcon class="edit-icon" name="edit" color="#2B2B2B"></SvgIcon
            >初次体验？开始您的分析
          </p>
          <p class="p2">
            选择场景并输入您希望分析的信息，或上传相关文件以生成实时分析。
          </p>
        </div>
        <SvgIcon class="step-icon" name="arrows-mark" color="#4895EF"></SvgIcon>
      </div>
      <div class="scenario-item">
        <div class="scenario-item-text">
          <p class="p1">
            <SvgIcon
              class="edit-icon"
              name="prime_upload"
              color="#2B2B2B"
            ></SvgIcon
            >上传您的代码文件
          </p>
          <p class="p2">
            已使用过我们的服务？上传之前导出的代码文件以继续分析。
          </p>
        </div>
        <SvgIcon class="step-icon" name="arrows-mark" color="#4895EF"></SvgIcon>
      </div>
    </div>
  </div>
</template>
<script setup>
import { ref, watch, reactive, nextTick } from "vue";
import Step from "../components/step-component.vue";
</script>

<style scoped lang="scss">
.main-content {
  .step {
    margin-top: 4.125em;
  }
  .intro {
    margin-top: 3.75em;
    text-align: center;
    h2 {
      color: var(--text-color);
      font-size: 2.5em;
      font-weight: 700;
      line-height: 200%;
    }
    p {
      margin-top: 1.875em;
      color: var(---intro-text-color);
      font-family: "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", sans-serif;
      font-size: 1.125em;
      line-height: 200%;
    }
  }
  .content {
    margin-top: 6.25em;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2.5em;
    .scenario-item {
      display: flex;
      width: 900px;
      justify-content: space-between;
      padding: 2em 3.56em 2em 2.5em;
      align-items: center;
      border-radius: 4px;
      border: 2px solid var(--blue-border-color);
      .scenario-item-text {
        .p1 {
          color: var(--text-color);
          font-size: 1.5em;
          line-height: 200%;
          display: flex;
          align-items: center;

          .edit-icon {
            margin-right: 0.4em;
          }
        }
        .p2 {
          color: var(--text-color);
          font-size: 1em;
          line-height: 200%;
        }
      }
    }
  }
}
</style>
