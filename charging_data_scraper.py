import pandas as pd
import random
import time
from datetime import datetime, timedelta
import os

class ChargingDataGenerator:
    """
    用于生成/采集2019年至2023年全国重点城市新能源汽车充电网络运营数据的脚本。
    如果需要真实爬取，请替换 `generate_mock_data` 中的逻辑为实际的 `requests.get` 或 `scrapy` 代码。
    """

    def __init__(self, total_records=55000):
        self.total_records = total_records
        self.cities = ['北京', '上海', '广州', '深圳', '杭州', '成都', '武汉', '西安', '南京', '重庆']
        self.districts = ['朝阳区', '海淀区', '浦东新区', '天河区', '南山区', '西湖区', '武侯区', '江汉区', '雁塔区', '鼓楼区']
        self.statuses = ['充电中', '空闲', '故障', '离线']
        self.start_date = datetime(2019, 1, 1)
        self.end_date = datetime(2023, 12, 31)

    def random_date(self, start, end):
        """生成指定范围内的随机时间"""
        delta = end - start
        int_delta = (delta.days * 24 * 60 * 60) + delta.seconds
        random_second = random.randrange(int_delta)
        return start + timedelta(seconds=random_second)

    def generate_mock_data(self):
        print(f"开始采集/生成 {self.total_records} 条数据...")
        data = []
        
        for i in range(self.total_records):
            city = random.choice(self.cities)
            # 模拟地理位置
            location = f"{city}市{random.choice(self.districts)}某充电站_{random.randint(1, 100)}号"
            
            # 模拟时间
            timestamp = self.random_date(self.start_date, self.end_date)
            
            # 模拟充电时长 (分钟)
            duration = random.randint(10, 180)
            
            # 模拟功率 (kW)
            power = random.choice([30.0, 60.0, 120.0, 150.0])
            
            # 模拟电价 (元/度)
            price = round(random.uniform(0.8, 1.8), 2)
            
            # 模拟使用状态
            status = random.choice(self.statuses)
            
            # 模拟充电量 (kWh) = 功率 * (时长/60) * 效率系数(0.9)
            if status == '充电中':
                energy = round(power * (duration / 60) * 0.9, 2)
            else:
                energy = 0.0
                duration = 0

            record = {
                "id": f"REC_{timestamp.strftime('%Y%m%d')}_{i:05d}",
                "city": city,
                "location": location,
                "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "status": status,
                "duration_minutes": duration,
                "power_kw": power,
                "price_per_kwh": price,
                "energy_kwh": energy
            }
            data.append(record)
            
            if (i + 1) % 10000 == 0:
                print(f"已处理 {i + 1} 条数据...")

        return pd.DataFrame(data)

    def save_to_csv(self, df, filename="charging_data_2019_2023.csv"):
        print(f"正在保存数据到 {filename} ...")
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        print("保存完成。")

if __name__ == "__main__":
    # 检查是否安装了pandas
    try:
        import pandas
    except ImportError:
        print("请先安装 pandas: pip install pandas")
        exit(1)

    generator = ChargingDataGenerator(total_records=52000) # 生成超过5万条
    df = generator.generate_mock_data()
    
    # 简单的数据预览
    print("\n数据预览:")
    print(df.head())
    print(f"\n数据统计:\n{df.describe()}")
    
    generator.save_to_csv(df)
