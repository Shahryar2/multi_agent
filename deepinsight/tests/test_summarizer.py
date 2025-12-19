import sys
import os

# 确保可以导入 deepinsight 包
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deepinsight.utils.summarizer import summarize_single_doc

def test_simple_summary():
    # 1. 模拟一个典型的长网页文档（超过 200 字以触发摘要逻辑）
    sample_doc = {
        "id": "test-001",
        "query": "2025年AI手机市场趋势",
        "title": "IDC：2025年将成为AI手机爆发元年",
        "text": """
        IDC近日发布了《2025年全球智能手机市场展望》。报告指出，随着生成式AI技术的成熟，2025年将成为AI手机的爆发元年。
        预计全球AI手机出货量将达到1.2亿台，同比增长超过150%。在中国市场，华为、小米、OPPO等厂商纷纷推出搭载端侧大模型的旗舰机型。
        这些手机不仅支持实时的语音翻译，还能实现复杂的图像编辑和智能助手功能。
        然而，硬件成本的上升也是一个不容忽视的问题。由于需要更高性能的NPU和更大的内存，AI手机的平均售价预计将上涨10%至15%。
        此外，电池续航和散热也是厂商面临的技术挑战。
        总的来说，AI手机正在改变用户的交互方式，并推动智能手机行业进入下一个增长周期。
        此外，报告还提到，苹果公司在2025年推出的新一代iPhone将全面集成自研的AI芯片，这可能会进一步加剧高端市场的竞争。
        三星则计划在其中端机型中也引入部分AI功能，以保持其在全球市场份额上的领先地位。
        """
    }

    print(f"--- [测试开始] 原始文档长度: {len(sample_doc['text'])} 字 ---")
    print(f"原始内容片段: {sample_doc['text'][:50]}...")

    # 2. 执行摘要
    try:
        result = summarize_single_doc(sample_doc)
        
        print("\n" + "="*50)
        print("--- [摘要结果] ---")
        print(f"标题: {result.get('title')}")
        print(f"摘要内容:\n{result.get('text')}")
        print("="*50)
        
        print(f"\n摘要后长度: {len(result.get('text'))} 字")
        print(f"压缩率: {round((1 - len(result.get('text'))/len(sample_doc['text']))*100, 2)}%")
        print(f"标记位 is_summary: {result.get('is_summary')}")

    except Exception as e:
        print(f"测试过程中出现错误: {e}")

if __name__ == "__main__":
    test_simple_summary()