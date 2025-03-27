import sys
from pathlib import Path

# 将项目根目录添加到Python路径
ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.append(str(ROOT_DIR))

from src.crawler.web_crawlers import ContentQualityClassifier

if __name__ == "__main__":
    classifier = ContentQualityClassifier()
    text = """
    记录代理人 ( AOR ) 是与保单持有人签订了符合合同签订地现行法律规范和法规的合同协议的个人或法人。记录代理人有权从相关保单中收取佣金。 [ 1 ]
    记录代理人有权代表投保人向指定保险公司购买、服务和维持保险。大多数保险公司不会向记录代理人以外的代理人透露信息或讨论投保人的账户。希望更换保险代理人的投保人必须适当授权保险公司披露其信息并与新任命的代理人讨论其保险范围，例如通过记录代理人函。 [ 2 ]
    相关文件可通过纸质或电子方式签署（在电子签署合法的司法管辖区）。申请可以电子形式提交，也可以以纸质形式提交。
    """
    print(len(text[:512]))
    is_high_quality, score = classifier.predict_quality(text[:512])
    print(f"Is high quality: {is_high_quality}, Score: {score}")
    
