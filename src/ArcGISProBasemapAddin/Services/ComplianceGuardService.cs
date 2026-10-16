using System;
using System.Collections.Generic;
using System.Linq;

namespace ArcGISProBasemapAddin.Services
{
    /// <summary>
    /// 国界触发制与图源合规守卫服务（严格对齐 docs/地图制作规范.md 第三节）
    /// </summary>
    public sealed class ComplianceGuardService
    {
        public static ComplianceGuardService Instance { get; } = new ComplianceGuardService();

        private static readonly HashSet<string> DomesticWhitelistIds = new(StringComparer.OrdinalIgnoreCase)
        {
            "amap_sat",
            "amap_road",
            "amap_label_only",
            "esri_imagery" // 纯遥感卫星影像不含国界线与争议行政标注，合规允许
        };

        private static readonly string[] PoisonedDomains =
        {
            "tile.openmaps.fr",
            "127.0.0.1:25412"
        };

        /// <summary>
        /// 校验在线图源在当前视野/国界条件下是否允许加载
        /// </summary>
        public (bool Allowed, string Reason) ValidateOnlineSource(string sourceId, string urlOrTemplate, bool hasNationalBorderInView, bool offlineMode)
        {
            if (offlineMode)
            {
                return (false, "当前已开启【纯离线断网模式】，已阻断所有在线瓦片源请求。");
            }

            if (!string.IsNullOrWhiteSpace(urlOrTemplate))
            {
                foreach (var bad in PoisonedDomains)
                {
                    if (urlOrTemplate.Contains(bad, StringComparison.OrdinalIgnoreCase))
                    {
                        return (false, $"已拦截已知污染或不可移植源：{bad}（防黑黄条纹报错瓦片或失效代理）。");
                    }
                }
            }

            if (hasNationalBorderInView && !DomesticWhitelistIds.Contains(sourceId))
            {
                return (false,
                    $"【国界触发制拦截】当前视图包含国界或宏观区域，依据《地图制作规范》第三节，禁止使用非白名单境外行政/地形底图（{sourceId}）。请改用高德纠偏底图、纯卫星影像或本地离线矢量底图。");
            }

            return (true, "合规校验通过");
        }

        /// <summary>
        /// 规范化港澳台地区标注名称（防止不规范简称）
        /// </summary>
        public string NormalizeRegionLabel(string rawLabel)
        {
            if (string.IsNullOrWhiteSpace(rawLabel)) return string.Empty;
            var result = rawLabel;
            if (result.Equals("台湾", StringComparison.OrdinalIgnoreCase) || result.Equals("Taiwan", StringComparison.OrdinalIgnoreCase))
                return "中国台湾";
            if (result.Equals("香港", StringComparison.OrdinalIgnoreCase) || result.Equals("Hong Kong", StringComparison.OrdinalIgnoreCase))
                return "中国香港";
            if (result.Equals("澳门", StringComparison.OrdinalIgnoreCase) || result.Equals("Macau", StringComparison.OrdinalIgnoreCase))
                return "中国澳门";
            return result;
        }
    }
}
