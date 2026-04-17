#!/bin/python
# -*- coding: utf8 -*-
import sys
import os
import re

class Solution:
    def zuiwan(self, n, m, ta, tb, k, ai, bi):
        # 动态规划：dp[i][j][t] = 取消i个A→B航班、j个B→C航班后的最晚到达时间
        # 简化：枚举所有可能的组合
        
        max_time = -1
        
        # 枚举取消A→B的i个航班，取消B→C的j个航班，其中i+j=k
        for i in range(k + 1):
            j = k - i
            if i > n or j > m:
                continue
            
            # 取消i个后，A→B还剩n-i个航班，选最晚的
            if n - i <= 0 or m - j <= 0:
                continue
            
            ai_sorted = sorted(ai, reverse=True)  # 降序
            bi_sorted = sorted(bi, reverse=True)  # 降序
            
            # 选择A→B中第i+1大的航班（取消最小的i个，选最大的）
            ab_depart = ai_sorted[i]
            ab_arrive = ab_depart + ta
            
            # 在B→C中找起飞时间 >= ab_arrive 的最晚航班
            best_bi = -1
            for depart in bi_sorted:
                if depart >= ab_arrive:
                    best_bi = depart
                    break
            
            # 如果找不到满足条件的B→C航班，跳过
            if best_bi == -1:
                continue
            
            arrive_time = best_bi + tb
            max_time = max(max_time, arrive_time)
        
        return max_time

n = int(input())
m = int(input())
ta = int(input())
tb = int(input())
k = int(input())
ai = list(map(int, input().split()))
bi = list(map(int, input().split()))

s = Solution()
res = s.zuiwan(n, m, ta, tb, k, ai, bi)

print(res)