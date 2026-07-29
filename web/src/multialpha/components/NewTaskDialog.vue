<template>
  <el-dialog v-model="visible" width="620px" title="新建因子挖掘任务" destroy-on-close>
    <el-tabs v-model="form.method"><el-tab-pane label="文字描述" name="text"/><el-tab-pane label="研报上传" name="pdf"/><el-tab-pane label="因子优化" name="optimize"/><el-tab-pane label="K线图片" name="image" disabled/><el-tab-pane label="交割单分析" name="trade" disabled/></el-tabs>
    <el-form label-position="top">
      <el-form-item v-if="form.method==='text'||form.method==='optimize'" :label="form.method==='text'?'策略描述':'优化目标'"><el-input v-model="form.description" type="textarea" :rows="5" placeholder="用自然语言描述你的策略思路…"/></el-form-item>
      <el-form-item v-if="form.method==='text'" label="挖掘场景"><el-select v-model="form.scenario" style="width:100%"><el-option label="因子挖掘 (fin_factor)" value="Finance Data Building"/><el-option label="量化全流程 (fin_quant)" value="Finance Whole Pipeline"/><el-option label="模型实现 (fin_model)" value="Finance Model Implementation"/></el-select></el-form-item>
      <el-form-item v-if="form.method==='text'||form.method==='optimize'" label="验证模型"><el-select v-model="form.modelSelector" style="width:100%"><el-option label="LightGBM（默认）" value="lgbm"/><el-option label="Linear（闭式 OLS，最快）" value="linear"/><el-option label="XGBoost" value="xgboost"/><el-option label="CatBoost" value="catboost"/></el-select></el-form-item>
      <el-form-item v-if="form.method==='pdf'||form.method==='optimize'" :label="form.method==='pdf'?'上传研报 PDF':'现有因子代码（可选）'"><el-upload drag multiple :auto-upload="false" :accept="form.method==='pdf'?'.pdf':'.py'" :on-change="onFileChange" :on-remove="onFileRemove"><div class="upload-copy">点击或拖拽文件到此处</div></el-upload></el-form-item>
      <el-form-item label="循环次数"><el-select v-model="form.loops"><el-option v-for="item in [1,3,5,10]" :key="item" :label="`${item} 轮`" :value="item"/></el-select></el-form-item>
      <el-form-item v-if="form.method==='text'" label="运行模式"><el-switch v-model="form.autoMode" active-text="全自动（每轮无需人工确认）" inactive-text="交互式（每轮可调整假设和反馈）" style="width:100%"/></el-form-item>
    </el-form>
    <template #footer><el-button @click="visible=false">取消</el-button><el-button type="primary" :loading="submitting" @click="submit">启动任务</el-button></template>
  </el-dialog>
</template>
<script setup lang="ts">
import { reactive,ref,watch } from 'vue';import type { UploadFile } from 'element-plus';import { ElMessage } from 'element-plus';import type { TaskMethod } from '../types'
const props=defineProps<{modelValue:boolean}>();const emit=defineEmits<{'update:modelValue':[value:boolean];submit:[value:{method:TaskMethod;description:string;scenario:string;loops:number;modelSelector:string;autoMode:boolean;files:File[]}]}>();const visible=ref(props.modelValue),submitting=ref(false),files=ref<File[]>([]);const form=reactive<{method:TaskMethod;description:string;scenario:string;loops:number;modelSelector:string;autoMode:boolean}>({method:'text',description:'',scenario:'Finance Data Building',loops:10,modelSelector:'lgbm',autoMode:true})
watch(()=>props.modelValue,value=>visible.value=value);watch(visible,value=>emit('update:modelValue',value));const onFileChange=(file:UploadFile)=>{if(file.raw&&!files.value.includes(file.raw))files.value.push(file.raw)};const onFileRemove=(file:UploadFile)=>files.value=files.value.filter(item=>item!==file.raw)
async function submit(){if((form.method==='text'||form.method==='optimize')&&!form.description.trim()){ElMessage.warning('请填写任务描述');return}if(form.method==='pdf'&&!files.value.length){ElMessage.warning('请上传研报 PDF');return}submitting.value=true;try{emit('submit',{...form,files:files.value})}finally{setTimeout(()=>submitting.value=false,500)}}
defineExpose({open:(method:TaskMethod='text')=>{form.method=method;visible.value=true},close:()=>visible.value=false})
</script>
