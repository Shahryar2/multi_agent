from graph.workflow import create_graph

app = create_graph()

# 必须指定 thread_id 来区分不同用户的会话
config = {"configurable": {"thread_id": "user-123"}}

print("--- 阶段 1: 启动任务，生成计划 ---")
inputs = {"task": "分析2025年AI手机市场", "max_revisions": 1, "revision_number": 0}

# 运行直到中断点
for event in app.stream(inputs, config=config):
    for k, v in event.items():
        print(f"完成节点: {k}")
        if k == "planner":
            print(f"生成的计划: {v['plan']}")

print("\n--- 阶段 2: 系统暂停，等待用户确认 ---")
# 获取当前状态
snapshot = app.get_state(config)
print("当前待执行的下一步:", snapshot.next)
print("当前计划:", snapshot.values["plan"])

user_input = input("是否满意该计划？(y/n，输入 n 可以修改计划): ")

if user_input.lower() == 'n':
    # 用户想修改计划
    new_plan_str = input("请输入新的计划 (逗号分隔): ")
    new_plan = new_plan_str.split(",")
    # 更新状态！
    app.update_state(config, {"plan": new_plan})
    print("计划已更新！")

print("\n--- 阶段 3: 继续执行 ---")
# 传入 None 表示继续执行
for event in app.stream(None, config=config):
    for k, v in event.items():
        print(f"完成节点: {k}")