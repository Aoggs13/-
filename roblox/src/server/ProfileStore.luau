--!strict
-- Dependency-injected persistence with renewable session leases.
-- Callers choose retry timing; failed loads never authorize writes.
local ProfileStore = {}
ProfileStore.__index = ProfileStore

local LEASE_SECONDS = 180

local function finite(value: any): boolean
	return type(value) == "number" and value == value and math.abs(value) < math.huge
end

local function field(value: any, maximum: number): number
	return if finite(value) then math.clamp(math.floor(value), 0, maximum) else 0
end

local function snapshot(profile: any)
	local source = if type(profile) == "table" then profile else {}
	if next(source) == nil then
		return {}
	end
	return {
		Coins = field(source.Coins, 1e9),
		Wins = field(source.Wins, 1e9),
		SpeedLevel = field(source.SpeedLevel, 3),
		BestHeight = field(source.BestHeight, 10000),
	}
end

function ProfileStore.new(store: any, sessionId: string, nowFn: () -> number)
	assert(type(sessionId) == "string" and sessionId ~= "", "A nonempty session ID is required")
	return setmetatable({
		store = store,
		sessionId = sessionId,
		now = nowFn,
		owned = {} :: { [number]: boolean },
	}, ProfileStore)
end

function ProfileStore.load(self: any, id: number): (any, boolean)
	local now = self.now()
	local ok, result = pcall(function()
		return self.store:UpdateAsync("player_" .. tostring(id), function(record: any): any
			local existing = if type(record) == "table" then record else {}
			local owner = existing.SessionId
			local lease = existing.LeaseUntil
			if type(owner) == "string" and owner ~= "" and owner ~= self.sessionId
				and finite(lease) and lease > now then
				return nil
			end
			local data = if type(existing.Profile) == "table" then existing.Profile else existing
			return {
				Profile = snapshot(data),
				SessionId = self.sessionId,
				LeaseUntil = now + LEASE_SECONDS,
			}
		end)
	end)
	if not ok or type(result) ~= "table" or result.SessionId ~= self.sessionId then
		return nil, false
	end
	self.owned[id] = true
	return snapshot(result.Profile), true
end

function ProfileStore.save(self: any, id: number, profile: any, release: boolean?): boolean
	if not self.owned[id] then
		return false
	end
	local now = self.now()
	local copied = snapshot(profile)
	local ok, result = pcall(function()
		return self.store:UpdateAsync("player_" .. tostring(id), function(record: any): any
			if type(record) ~= "table" or record.SessionId ~= self.sessionId then
				return nil
			end
			return {
				Profile = copied,
				SessionId = if release then "" else self.sessionId,
				LeaseUntil = if release then 0 else now + LEASE_SECONDS,
			}
		end)
	end)
	local expectedOwner = if release then "" else self.sessionId
	if not ok or type(result) ~= "table" or result.SessionId ~= expectedOwner then
		return false
	end
	if release then
		self.owned[id] = nil
	end
	return true
end

return ProfileStore
