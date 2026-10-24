--!strict
-- Shared, deterministic rules. No Roblox services are needed to run this module.
local Rules = {
	RoundSeconds = 95,
	IntermissionSeconds = 12,
	CountdownSeconds = 5,
	StageCount = 24,
	StageRise = 3.6,
	CoinValue = 3,
	WinCoins = 30,
	SurvivalCoins = 5,
	MinSurvivalSeconds = 20,
	DashCooldown = 4,
	DashSpeed = 60,
	LavaStart = -6,
	LavaEnd = 89,
	LavaGraceSeconds = 12,
	MaxUpgradeLevel = 3,
}

local upgradeCosts = table.freeze({ 30, 65, 110 })

local function finite(value: number): boolean
	return value == value and math.abs(value) < math.huge
end

function Rules.lavaHeight(elapsed: number): number
	-- Keep the first twelve seconds safe, then rise to the summit over the round.
	if elapsed ~= elapsed then
		elapsed = 0
	end
	local progress = math.clamp(
		(elapsed - Rules.LavaGraceSeconds) / (Rules.RoundSeconds - Rules.LavaGraceSeconds),
		0,
		1
	)
	return Rules.LavaStart + (Rules.LavaEnd - Rules.LavaStart) * progress
end

function Rules.upgradeCost(level: number): number?
	-- A level denotes the upgrades already owned. Invalid levels cannot be bought.
	if not finite(level) or level < 0 or level >= Rules.MaxUpgradeLevel or level % 1 ~= 0 then
		return nil
	end
	return upgradeCosts[level + 1]
end

function Rules.walkSpeed(level: number): number
	if not finite(level) then
		level = 0
	end
	return 18 + 2 * math.clamp(math.floor(level), 0, Rules.MaxUpgradeLevel)
end

function Rules.canPurchase(balance: number, level: number): boolean
	local cost = Rules.upgradeCost(level)
	return finite(balance) and cost ~= nil and balance >= cost
end

function Rules.roundReward(escaped: boolean): number
	return if escaped then Rules.WinCoins else Rules.SurvivalCoins
end

function Rules.formatTime(seconds: number): string
	if not finite(seconds) then
		seconds = 0
	end
	local wholeSeconds = math.max(0, math.floor(seconds))
	return string.format("%d:%02d", math.floor(wholeSeconds / 60), wholeSeconds % 60)
end

return table.freeze(Rules)
