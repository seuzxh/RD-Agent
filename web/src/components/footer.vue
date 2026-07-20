<template>
  <footer>
    <div class="footer" :style="{ background: color }">
      <p>
        <a target="_blank" aria-label="联系我们" href="#">联系我们</a>
        <span class="line">|</span>
        <a
          target="_blank"
          aria-label="隐私与 Cookie"
          href="#"
          >隐私与 Cookie</a
        >
        <span class="line">|</span>
        <a
          target="_blank"
          aria-label="使用条款"
          href="#"
          >使用条款</a
        >
        <span class="line">|</span>
        <a
          target="_blank"
          aria-label="商标"
          href="#"
          >商标</a
        >
        <span class="line">|</span>
        <span style="">© crsec 2026</span>
        <span class="line">|</span>
        <span
          >本内容由 AI 生成，可能并非完全准确或最新；涉及重要事项时，请向专业人士核实。</span
        >
      </p>
    </div>
  </footer>
</template>
<script>
export default {
  components: {},
  props: {
    color: {
      type: String,
      required: true,
    },
  },
  setup() {},
};
</script>
<style scoped lang="scss">
.footer {
  padding: 1.75em 4.375em;
  box-sizing: border-box;
  text-align: center;
  width: 100%;
  color: var(--footer-text-color);
  // background: var(--bg-grey);
  // background: var(--bg-white);
  font-size: 12px;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  flex-direction: row;
  position: relative;
  a {
    color: var(--footer-text-color);
    font-weight: 400;
    font-size: 12px;
    line-height: 21px;
    text-decoration: none;
    display: inline-block;
  }
  .line {
    margin: 0 16px;
    display: inline-block;
    vertical-align: top;
  }
  p {
    display: flex;
    align-items: center;
    margin: 0;

    &:nth-child(2) a {
      display: inline-block;
      img {
        height: 1.375em;
        vertical-align: middle;
      }
    }
  }
}
</style>
