-- Run from roblox/: luau tests/rules.spec.luau
local Rules = require("../src/shared/Rules")

local passed = 0
local function test(name, run)
	local ok, problem = pcall(run)
	if not ok then
		error(name .. ": " .. tostring(problem), 0)
	end
	passed += 1
	print("PASS " .. name)
end

local function near(actual, expected)
	assert(math.abs(actual - expected) < 0.000001, tostring(actual) .. " ~= " .. tostring(expected))
end

test("lava respects grace, midpoint and round bounds", function()
	near(Rules.lavaHeight(-100), Rules.LavaStart)
	near(Rules.lavaHeight(0), Rules.LavaStart)
	near(Rules.lavaHeight(12), Rules.LavaStart)
	near(Rules.lavaHeight(12 + (95 - 12) / 2), (Rules.LavaStart + Rules.LavaEnd) / 2)
	near(Rules.lavaHeight(95), Rules.LavaEnd)
	near(Rules.lavaHeight(1000), Rules.LavaEnd)
end)

test("lava never retreats or exceeds configured heights", function()
	local previous = Rules.LavaStart
	for step = 0, Rules.RoundSeconds * 10 do
		local height = Rules.lavaHeight(step / 10)
		assert(height >= previous)
		assert(height >= Rules.LavaStart and height <= Rules.LavaEnd)
		previous = height
	end
end)

test("upgrades enforce price, level and maximum", function()
	assert(Rules.upgradeCost(0) == 30)
	assert(Rules.upgradeCost(1) == 65)
	assert(Rules.upgradeCost(2) == 110)
	assert(Rules.upgradeCost(3) == nil)
	assert(Rules.upgradeCost(-1) == nil)
	assert(Rules.upgradeCost(0.5) == nil)
	assert(not Rules.canPurchase(29, 0))
	assert(Rules.canPurchase(30, 0))
	assert(Rules.canPurchase(31, 0))
	assert(not Rules.canPurchase(-1, 0))
	assert(not Rules.canPurchase(1000, 3))
end)

test("a complete purchase progression spends exactly the intended coins", function()
	local balance, level = 205, 0
	while Rules.canPurchase(balance, level) do
		balance -= Rules.upgradeCost(level)
		level += 1
	end
	assert(level == Rules.MaxUpgradeLevel)
	assert(balance == 0)
	assert(not Rules.canPurchase(balance, level))
end)

test("speed progresses and remains bounded", function()
	assert(Rules.walkSpeed(0) == 18)
	assert(Rules.walkSpeed(1) == 20)
	assert(Rules.walkSpeed(2) == 22)
	assert(Rules.walkSpeed(3) == 24)
	assert(Rules.walkSpeed(-100) == 18)
	assert(Rules.walkSpeed(100) == 24)
	assert(Rules.walkSpeed(1.9) == 20)
end)

test("escape and survival rewards differ", function()
	assert(Rules.roundReward(true) == 30)
	assert(Rules.roundReward(false) == 5)
	assert(Rules.roundReward(true) > Rules.roundReward(false))
end)

test("timer floors partial seconds and pads seconds", function()
	assert(Rules.formatTime(-1) == "0:00")
	assert(Rules.formatTime(0) == "0:00")
	assert(Rules.formatTime(9.9) == "0:09")
	assert(Rules.formatTime(59) == "0:59")
	assert(Rules.formatTime(60) == "1:00")
	assert(Rules.formatTime(95) == "1:35")
	assert(Rules.formatTime(125) == "2:05")
end)

test("invalid numeric values cannot buy upgrades or corrupt gameplay", function()
	local nan = 0 / 0
	assert(Rules.upgradeCost(nan) == nil)
	assert(Rules.upgradeCost(math.huge) == nil)
	assert(not Rules.canPurchase(nan, 0))
	assert(not Rules.canPurchase(math.huge, 0))
	assert(Rules.walkSpeed(nan) == 18)
	near(Rules.lavaHeight(nan), Rules.LavaStart)
	near(Rules.lavaHeight(math.huge), Rules.LavaEnd)
	assert(Rules.formatTime(nan) == "0:00")
end)

test("rule exports are immutable", function()
	local ok = pcall(function()
		Rules.WinCoins = 999999
	end)
	assert(not ok)
	assert(Rules.WinCoins == 30)
end)

print(string.format("%d rule tests passed", passed))
