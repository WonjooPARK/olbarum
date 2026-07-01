const fs = require("fs");
const path = require("path");
const readline = require("readline");

const playwrightCorePath =
  "C:\\Users\\wjpark\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\node_modules\\.pnpm\\playwright-core@1.61.1\\node_modules\\playwright-core";
const { chromium } = require(playwrightCorePath);

const BUSINESS_ID = "798392";
const CHROME_PATH = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const NEXT_TEXT = "\ub2e4\uc74c\ub2e8\uacc4";
const SELECT_DATE_TEXT = "\ub0a0\uc9dc\uc640 \uc2dc\uac04\uc744 \uc120\ud0dd\ud574 \uc8fc\uc138\uc694";

const PRODUCTS = {
  director: { bizItemId: "4725840" },
  manager: { bizItemId: "5000239" },
  sunday: { bizItemId: "6775999" },
  trial30: { bizItemId: "6155711" },
};

function parseArgs(argv) {
  const args = {
    product: "director",
    headed: true,
    autoRequired: true,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--headless") args.headed = false;
    else if (arg === "--no-auto-required") args.autoRequired = false;
    else if (arg.startsWith("--")) {
      args[arg.slice(2)] = argv[i + 1];
      i += 1;
    }
  }
  return args;
}

function readEnvFile() {
  const envPath = path.resolve(process.cwd(), ".env");
  if (!fs.existsSync(envPath)) return {};
  const values = {};
  for (const rawLine of fs.readFileSync(envPath, "utf8").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const [rawKey, ...rest] = line.split("=");
    let value = rest.join("=").trim();
    if (
      value.length >= 2 &&
      value[0] === value[value.length - 1] &&
      ["'", '"'].includes(value[0])
    ) {
      value = value.slice(1, -1);
    }
    values[rawKey.trim()] = value;
  }
  return values;
}

function credentials() {
  const env = readEnvFile();
  return {
    id: process.env.NAVER_ID || env.NAVER_ID || "",
    password: process.env.NAVER_PASSWORD || env.NAVER_PASSWORD || "",
  };
}

function bookingUrl(product, date) {
  const params = new URLSearchParams({
    area: "pll",
    lang: "ko",
    "service-target": "map-pc",
    theme: "place",
    startDate: date,
  });
  return `https://m.booking.naver.com/booking/13/bizes/${BUSINESS_ID}/items/${product.bizItemId}?${params}`;
}

function normalizeTimeLabel(time) {
  const [rawHour, minute] = time.split(":");
  const hour = Number(rawHour);
  if (!Number.isInteger(hour) || !minute) {
    throw new Error("--time must be HH:MM, for example 13:30");
  }
  if (hour === 0) return `12:${minute}`;
  if (hour > 12) return `${hour - 12}:${minute}`;
  return `${hour}:${minute}`;
}

function addMinutes(time, minutesToAdd) {
  const [rawHour, rawMinute] = time.split(":");
  const date = new Date(2000, 0, 1, Number(rawHour), Number(rawMinute));
  date.setMinutes(date.getMinutes() + minutesToAdd);
  const hour = String(date.getHours()).padStart(2, "0");
  const minute = String(date.getMinutes()).padStart(2, "0");
  return `${hour}:${minute}`;
}

function consecutiveTimeLabels(startTime, duration) {
  const slotCount = Number(duration) / 30;
  if (!Number.isInteger(slotCount) || slotCount < 1) {
    throw new Error("--option must be a positive 30-minute multiple");
  }
  return Array.from({ length: slotCount }, (_, index) =>
    normalizeTimeLabel(addMinutes(startTime, index * 30))
  );
}

async function clickButtonByExactText(page, text) {
  const clicked = await page.evaluate((targetText) => {
    const buttons = Array.from(document.querySelectorAll("button"));
    const button = buttons.find(
      (candidate) =>
        (candidate.textContent || "").replace(/\s+/g, " ").trim() === targetText &&
        !candidate.disabled &&
        candidate.getAttribute("aria-disabled") !== "true"
    );
    if (!button) return false;
    button.scrollIntoView({ block: "center" });
    button.click();
    return true;
  }, text);
  if (!clicked) throw new Error(`Could not click button: ${text}`);
}

async function selectTime(page, time) {
  const label = normalizeTimeLabel(time);
  await clickButtonByExactText(page, label);
}

async function selectConsecutiveTimes(page, startTime, duration) {
  const labels = consecutiveTimeLabels(startTime, duration);
  for (const label of labels) {
    await clickButtonByExactText(page, label);
    await page.waitForTimeout(200);
  }
}

async function selectDurationOption(page, duration) {
  const escapedDuration = String(duration).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const checkbox = page.getByRole("checkbox", {
    name: new RegExp(`\\(${escapedDuration}\\ubd84\\)`),
  });
  const count = await checkbox.count();
  if (count < 1) return false;
  await checkbox.first().check({ force: true });
  return true;
}

async function clickNext(page) {
  await clickButtonByExactText(page, NEXT_TEXT);
}

async function maybeLogin(page, creds) {
  await page.waitForTimeout(1500);
  const idInput = page.locator("#id");
  if ((await idInput.count()) === 0) return false;
  if (!creds.id || !creds.password) {
    throw new Error("Login page appeared, but NAVER_ID/NAVER_PASSWORD are not set.");
  }
  await idInput.fill(creds.id);
  await page.locator("#pw").fill(creds.password);
  await page.locator("#log\\.login, button[type='submit']").first().click();
  await page.waitForTimeout(3000);
  return true;
}

async function checkRequiredBoxes(page) {
  const requiredCheckboxes = page
    .getByRole("checkbox")
    .filter({ hasText: /필수|예약취소|방문경로|당일취소|부득이한/ });
  const count = await requiredCheckboxes.count();
  for (let i = 0; i < count; i += 1) {
    const item = requiredCheckboxes.nth(i);
    if (!(await item.isChecked().catch(() => false))) {
      await item.check({ force: true }).catch(() => {});
    }
  }
}

function waitForEnter(message) {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });
  return new Promise((resolve) => {
    rl.question(message, () => {
      rl.close();
      resolve();
    });
  });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.date || !args.time || !args.option) {
    throw new Error(
      "Usage: node backend/naver_reserve_prepare.cjs --date YYYY-MM-DD --time HH:MM --option 90 [--product director]"
    );
  }
  const product = PRODUCTS[args.product];
  if (!product) throw new Error(`Unknown product: ${args.product}`);

  const browser = await chromium.launch({
    headless: !args.headed,
    executablePath: CHROME_PATH,
  });
  const page = await browser.newPage({ locale: "ko-KR" });
  await page.goto(bookingUrl(product, args.date), {
    waitUntil: "domcontentloaded",
    timeout: 30000,
  });

  await page.waitForSelector(`text=${SELECT_DATE_TEXT}`, { timeout: 20000 });
  await selectConsecutiveTimes(page, args.time, args.option);
  await selectDurationOption(page, args.option);
  await clickNext(page);

  const didLogin = await maybeLogin(page, credentials());
  if (didLogin) {
    await page.waitForSelector(`text=${SELECT_DATE_TEXT}`, { timeout: 20000 }).catch(
      () => {}
    );
    if (await page.getByText(SELECT_DATE_TEXT).count().catch(() => 0)) {
      await selectConsecutiveTimes(page, args.time, args.option);
      await selectDurationOption(page, args.option);
      await clickNext(page);
    }
  }

  if (args.autoRequired) {
    await checkRequiredBoxes(page);
  }

  console.log(
    JSON.stringify(
      {
        status: "prepared",
        message:
          "Reservation page is prepared. Review the page manually before pressing the final reservation button.",
        product: args.product,
        date: args.date,
        time: args.time,
        optionMinutes: args.option,
        url: page.url(),
      },
      null,
      2
    )
  );

  if (args.headed) {
    await waitForEnter("Review the browser. Press Enter here to close it...");
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error.stack || String(error));
  process.exit(1);
});
