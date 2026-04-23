#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_WIDTH = 1200;
const DEFAULT_HEIGHT = 720;
const FONT_FAMILY = [
  "Noto Sans CJK SC",
  "PingFang SC",
  "Microsoft YaHei",
  "SimHei",
  "Arial Unicode MS",
  "sans-serif",
].join(", ");

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    if (key.startsWith("--")) {
      const name = key.slice(2);
      const next = argv[index + 1];
      if (!next || next.startsWith("--")) {
        args[name] = true;
      } else {
        args[name] = next;
        index += 1;
      }
    }
  }
  return args;
}

function fail(message) {
  console.error(message);
  process.exit(1);
}

function safeFileName(value) {
  return String(value || "chart").replace(/[^\p{L}\p{N}._-]+/gu, "_").slice(0, 90);
}

function normalizeCharts(payload, args, specDir) {
  const charts = Array.isArray(payload) ? payload : payload.charts || [payload];
  return charts.map((chart, index) => {
    const id = chart.id || chart.chart_id || `CH${String(index + 1).padStart(2, "0")}`;
    let output = chart.output || chart.output_file;
    if (!output) {
      if (!args["output-dir"] && !args.output) {
        fail("批量渲染需要在图表规格中提供 output，或传入 --output-dir。");
      }
      output = args.output || path.join(args["output-dir"], `${safeFileName(id)}_${safeFileName(chart.title)}.png`);
    }
    if (!path.isAbsolute(output)) {
      output = path.resolve(specDir, output);
    }
    return {
      ...chart,
      id,
      output,
      width: Number(chart.width || args.width || DEFAULT_WIDTH),
      height: Number(chart.height || args.height || DEFAULT_HEIGHT),
    };
  });
}

function seriesType(chartType) {
  if (chartType === "column") return "bar";
  if (chartType === "ring") return "pie";
  return chartType || "line";
}

function buildOption(spec) {
  const chartType = spec.type || "line";
  const xValues = spec.x || spec.labels || [];
  const series = spec.series || [];
  const hasRateSeries = series.some((item) => item.yAxisIndex === 1 || item.axis === "right" || item.value_type === "percent");

  const base = {
    animation: false,
    backgroundColor: "#ffffff",
    color: ["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c", "#0891b2"],
    title: {
      text: spec.title || "",
      subtext: spec.subtitle || "",
      left: 28,
      top: 18,
      textStyle: { fontFamily: FONT_FAMILY, fontSize: 24, fontWeight: 700, color: "#111827" },
      subtextStyle: { fontFamily: FONT_FAMILY, fontSize: 13, color: "#4b5563" },
    },
    legend: { top: 78, left: 28, textStyle: { fontFamily: FONT_FAMILY, color: "#374151" } },
    tooltip: { trigger: chartType === "pie" || chartType === "ring" ? "item" : "axis" },
    grid: { left: 72, right: hasRateSeries ? 72 : 34, top: 132, bottom: 86, containLabel: true },
  };

  if (chartType === "pie" || chartType === "ring") {
    const pieData = xValues.map((name, index) => ({
      name,
      value: Number(series[0]?.data?.[index] || 0),
    }));
    return {
      ...base,
      series: [{
        name: series[0]?.name || spec.title || "指标",
        type: "pie",
        radius: chartType === "ring" ? ["42%", "68%"] : "66%",
        center: ["50%", "56%"],
        data: pieData,
        label: { fontFamily: FONT_FAMILY, formatter: "{b}: {d}%" },
      }],
    };
  }

  return {
    ...base,
    xAxis: {
      type: "category",
      data: xValues,
      axisLabel: { fontFamily: FONT_FAMILY, rotate: spec.x_rotate ?? (xValues.length > 8 ? 28 : 0), color: "#374151" },
      axisLine: { lineStyle: { color: "#9ca3af" } },
    },
    yAxis: [
      {
        type: "value",
        name: spec.y_label || "",
        nameTextStyle: { fontFamily: FONT_FAMILY, color: "#4b5563" },
        axisLabel: { fontFamily: FONT_FAMILY, color: "#4b5563" },
        splitLine: { lineStyle: { color: "#e5e7eb" } },
      },
      ...(hasRateSeries ? [{
        type: "value",
        name: spec.y2_label || "比例",
        min: 0,
        max: 1,
        axisLabel: { fontFamily: FONT_FAMILY, formatter: (value) => `${Math.round(value * 100)}%`, color: "#4b5563" },
        splitLine: { show: false },
      }] : []),
    ],
    series: series.map((item) => {
      const type = seriesType(item.type || chartType);
      const isRate = item.yAxisIndex === 1 || item.axis === "right" || item.value_type === "percent";
      return {
        name: item.name || "指标",
        type,
        yAxisIndex: isRate ? 1 : 0,
        smooth: type === "line" ? item.smooth !== false : undefined,
        barMaxWidth: type === "bar" ? 48 : undefined,
        data: item.data || [],
        label: item.label === false ? undefined : { show: Boolean(item.label), position: "top", fontFamily: FONT_FAMILY },
      };
    }),
  };
}

async function renderCharts(charts) {
  let puppeteer;
  let echartsPath;
  try {
    puppeteer = (await import("puppeteer")).default;
    echartsPath = require.resolve("echarts/dist/echarts.min.js");
  } catch (error) {
    fail(`ECharts PNG 渲染依赖不可用。请在技能目录执行 npm install。\n${error?.message || error}`);
  }

  const browser = await puppeteer.launch({
    headless: "new",
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });
  try {
    const page = await browser.newPage();
    for (const chart of charts) {
      await page.setViewport({ width: chart.width, height: chart.height, deviceScaleFactor: 2 });
      await page.setContent(`
        <!doctype html>
        <html lang="zh-CN">
          <head>
            <meta charset="utf-8" />
            <style>
              html, body { margin: 0; padding: 0; background: white; }
              #chart { width: ${chart.width}px; height: ${chart.height}px; font-family: ${FONT_FAMILY}; }
            </style>
          </head>
          <body><main id="chart"></main></body>
        </html>
      `);
      await page.addScriptTag({ path: echartsPath });
      const option = buildOption(chart);
      await page.evaluate((nextOption) => {
        const instance = window.echarts.init(document.getElementById("chart"), null, { renderer: "canvas" });
        instance.setOption(nextOption);
      }, option);
      const target = path.resolve(chart.output);
      await fs.mkdir(path.dirname(target), { recursive: true });
      const element = await page.$("#chart");
      await element.screenshot({ path: target, type: "png" });
      console.log(target);
    }
  } finally {
    await browser.close();
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const specPath = args.spec || args.specs;
  if (!specPath) {
    fail("用法：node scripts/render_echarts_png.mjs --spec chart.json --output chart.png，或 --specs chart_specs.json --output-dir charts");
  }
  const resolvedSpecPath = path.resolve(specPath);
  const payload = JSON.parse(await fs.readFile(resolvedSpecPath, "utf8"));
  const charts = normalizeCharts(payload, args, path.dirname(resolvedSpecPath));
  if (args.output && charts.length > 1) {
    fail("--output 只适用于单张图；批量渲染请使用 --output-dir 或在每个 chart 中提供 output。");
  }
  await renderCharts(charts);
}

main();
