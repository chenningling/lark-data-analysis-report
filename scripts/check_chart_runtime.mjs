#!/usr/bin/env node
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

async function main() {
  let puppeteer;
  let echartsPath;
  try {
    puppeteer = (await import("puppeteer")).default;
    echartsPath = require.resolve("echarts/dist/echarts.min.js");
  } catch (error) {
    console.error("ECharts PNG 渲染依赖不可用。请在技能目录执行：npm install");
    console.error(String(error?.message || error));
    process.exit(1);
  }

  let browser;
  try {
    browser = await puppeteer.launch({
      headless: "new",
      args: ["--no-sandbox", "--disable-setuid-sandbox"],
    });
    const page = await browser.newPage();
    await page.setViewport({ width: 800, height: 480, deviceScaleFactor: 2 });
    await page.setContent('<main id="chart" style="width:800px;height:480px"></main>');
    await page.addScriptTag({ path: echartsPath });
    await page.evaluate(() => {
      const chart = window.echarts.init(document.getElementById("chart"));
      chart.setOption({
        animation: false,
        title: { text: "渲染检查" },
        xAxis: { type: "category", data: ["A", "B"] },
        yAxis: { type: "value" },
        series: [{ type: "bar", data: [1, 2] }],
      });
    });
    console.log("ECharts PNG 渲染环境可用。");
  } catch (error) {
    console.error("Chromium/ECharts 渲染检查失败。");
    console.error(String(error?.message || error));
    process.exitCode = 1;
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

main();
