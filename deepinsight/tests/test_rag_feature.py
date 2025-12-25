import sys
import os
import time

# 将项目根目录添加到 python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deepinsight.graph.workflow import create_graph
from deepinsight.tools.vector_store import vector_store

def test_real_rag_flow():
    print("========================================")
    print("   DeepInsight RAG 全流程真实测试")
    print("   (Planner -> Search -> VectorStore -> Writer)")
    print("========================================")

    # 1. 环境清理
    print("\n[Step 0] 清空向量库...")
    vector_store.clear()

    # 2. 初始化 Graph
    app = create_graph()
    # 使用唯一的 thread_id 避免混淆
    thread_id = f"test_rag_{int(time.time())}"
    config = {"configurable": {"thread_id": thread_id}}

    # 3. 定义真实任务
    task = "分析2025年诺贝尔物理学奖得主及其主要贡献"
    print(f"\n[Step 1] 启动任务: {task}")
    
    inputs = {
        "task": task,
        "max_revisions": 1, 
        "revision_number": 0
    }

    # 4. 自动执行工作流
    # 这里的逻辑是：只要流程暂停（interrupt），就自动继续，直到结束
    print("\n[Step 2] 开始执行...")
    
    # 第一次启动
    current_input = inputs
    
    # 循环处理中断，直到流程结束
    while True:
        # 运行当前片段
        for event in app.stream(current_input, config=config):
            for k, v in event.items():
                print(f"✅ 完成节点: {k}")
                
                # 监控 Planner
                if k == "planner":
                    plan = v.get("plan", [])
                    print(f"   -> 生成计划: {len(plan)} 个步骤")
                    for i, step in enumerate(plan):
                        print(f"      {i+1}. {step.get('description')}")

                # 监控 Researcher
                if k == "researcher":
                    print(f"   -> Researcher 完成搜索与入库")

                # 监控 Writer
                if k == "writer":
                    print("\n" + "="*40)
                    print("   [Writer 生成的最终报告 (RAG结果)]")
                    print("="*40)
                    draft = v.get("draft", "")
                    # 打印前 800 字预览
                    print(draft)
                    print("="*40)

        # 检查是否还有下一步（处理 interrupt_before）
        snapshot = app.get_state(config)
        if not snapshot.next:
            print("\n🎉 流程执行完毕！")
            break
        
        print(f"\n[系统暂停] 下一步是: {snapshot.next}，正在自动继续...")
        current_input = None # 继续执行时不需要输入

    # 5. 最终验证向量库
    print("\n[Step 3] 验证向量库存储情况...")
    # 搜索一个肯定在报告里的关键词
    test_query = "Hopfield" 
    results = vector_store.similarity_search(test_query, k=3)
    
    if results:
        print(f"✅ 向量库验证成功！关键词 '{test_query}' 命中 {len(results)} 条结果：")
        for i, res in enumerate(results):
            title = res.get('title', '无标题')
            source = res.get('url', '未知来源')
            print(f"   [{i+1}] {title} \n       Source: {source}")
    else:
        print("❌ 警告：向量库检索为空，请检查 Researcher 是否成功存入数据。")

if __name__ == "__main__":
    test_real_rag_flow()