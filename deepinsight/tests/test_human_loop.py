from graph.workflow import create_graph

def run_demo():
    app = create_graph()

    # 必须指定 thread_id 来区分不同用户的会话（用于 SqliteSaver）
    config = {"configurable": {"thread_id": "user-123"}}

    print("--- 阶段 1: 启动任务，生成计划（运行到中断） ---")
    inputs = {"task": "分析2025年AI手机市场", "max_revisions": 1, "revision_number": 0}

    # 运行直到中断点（interrupt_before=["researcher"]）
    initial_events = []
    for event in app.stream(inputs, config=config):
        for k, v in event.items():
            print(f"完成节点: {k}")
            if k == "planner":
                print(f"生成的计划: {v.get('plan')}")
            initial_events.append((k, v))

    print("\n--- 阶段 2: 系统已暂停，检查状态并自动确认计划 ---")
    snapshot = app.get_state(config)
    print("当前待执行的下一步:", snapshot.next)
    print("当前计划:", snapshot.values.get("plan"))

    # 自动确认（如果你要手动修改计划可在此调用 app.update_state）
    # 继续执行
    print("\n--- 阶段 3: 继续执行（自动） ---")
    final_events = []
    for event in app.stream(None, config=config):
        for k, v in event.items():
            print(f"完成节点: {k}")
            final_events.append((k, v))

    # 简要检查 writer & reviewer 输出
    for k, v in final_events:
        if k == "writer":
            draft = v.get("draft") if isinstance(v, dict) else v
            print("\n--- Writer Draft (片段) ---")
            if isinstance(draft, str):
                print(draft[:1000])
            else:
                print(draft)
        if k == "reviewer":
            print("\n--- Reviewer 输出 ---")
            print(v)

if __name__ == "__main__":
    run_demo()