--!strict
-- Server-owned progression and round settlement, independent of Roblox services.
local Rules = require("./Rules")

local GameState = {}
GameState.__index = GameState

local function finite(value: any): boolean
	return type(value) == "number" and value == value and math.abs(value) < math.huge
end

local function integer(value: any, maximum: number): number
	if not finite(value) then
		return 0
	end
	return math.clamp(math.floor(value), 0, maximum)
end

local function time(value: number): number
	return if finite(value) then value else 0
end

function GameState.new()
	return setmetatable({
		profiles = {} :: { [number]: any },
		participants = {} :: { [number]: any },
		active = false,
	}, GameState)
end

function GameState.addPlayer(self: any, id: number, data: any?)
	if self.profiles[id] then
		return self.profiles[id]
	end
	local source = if type(data) == "table" then data else {}
	local profile = {
		Coins = integer(source.Coins, 1e9),
		Wins = integer(source.Wins, 1e9),
		SpeedLevel = integer(source.SpeedLevel, Rules.MaxUpgradeLevel),
		BestHeight = integer(source.BestHeight, 10000),
	}
	self.profiles[id] = profile
	return profile
end

function GameState.removePlayer(self: any, id: number)
	self.profiles[id] = nil
	self.participants[id] = nil
end

function GameState.startRound(self: any, ids: { number }, now: number)
	self.participants = {}
	self.active = true
	for _, id in ids do
		if self.profiles[id] then
			self.participants[id] = {
				Alive = true,
				Escaped = false,
				StartedAt = time(now),
				EndedAt = nil,
				Collected = {},
				DashReadyAt = 0,
			}
		end
	end
end

function GameState.getParticipant(self: any, id: number)
	return self.participants[id]
end

local function alive(self: any, id: number)
	local participant = self.participants[id]
	if self.active and self.profiles[id] and participant and participant.Alive then
		return participant
	end
	return nil
end

function GameState.eliminate(self: any, id: number, now: number): boolean
	local participant = alive(self, id)
	if not participant then
		return false
	end
	participant.Alive = false
	participant.EndedAt = time(now)
	return true
end

function GameState.escape(self: any, id: number, now: number): boolean
	local participant = alive(self, id)
	if not participant then
		return false
	end
	participant.Alive = false
	participant.Escaped = true
	participant.EndedAt = time(now)
	return true
end

function GameState.collect(self: any, id: number, key: any): boolean
	local participant = alive(self, id)
	if not participant or key == nil or participant.Collected[key] then
		return false
	end
	participant.Collected[key] = true
	local profile = self.profiles[id]
	profile.Coins = math.min(1e9, profile.Coins + Rules.CoinValue)
	return true
end

function GameState.dash(self: any, id: number, now: number): boolean
	local participant = alive(self, id)
	if not participant or not finite(now) or now < participant.DashReadyAt then
		return false
	end
	participant.DashReadyAt = now + Rules.DashCooldown
	return true
end

function GameState.upgrade(self: any, id: number): boolean
	local profile = self.profiles[id]
	if not profile or not Rules.canPurchase(profile.Coins, profile.SpeedLevel) then
		return false
	end
	local cost = Rules.upgradeCost(profile.SpeedLevel)
	assert(cost)
	profile.Coins -= cost
	profile.SpeedLevel += 1
	return true
end

function GameState.recordHeight(self: any, id: number, height: number)
	if not alive(self, id) or not finite(height) then
		return
	end
	local profile = self.profiles[id]
	profile.BestHeight = math.max(profile.BestHeight, integer(height, 10000))
end

function GameState.finishRound(self: any, now: number): { [number]: number }
	local rewards = {}
	if not self.active then
		return rewards
	end
	-- Settle once, even when finishRound is called twice by two server paths.
	self.active = false
	for id, participant in self.participants do
		local profile = self.profiles[id]
		if profile then
			local reward = 0
			if participant.Escaped then
				profile.Wins = math.min(1e9, profile.Wins + 1)
				reward = Rules.WinCoins
			elseif (participant.EndedAt or time(now)) - participant.StartedAt >= Rules.MinSurvivalSeconds then
				reward = Rules.SurvivalCoins
			end
			profile.Coins = math.min(1e9, profile.Coins + reward)
			rewards[id] = reward
		end
	end
	return rewards
end

return GameState
