--!strict
-- A repeatable route keeps every jump fair while each seed changes the climb.
local Rules = require("./Rules")

local MapPlan = {}

local function point(index: number, direction: number)
	local angle = math.rad(index * 30 * direction)
	return {
		X = math.sin(angle) * 20,
		Y = index * Rules.StageRise,
		Z = math.cos(angle) * 20,
	}
end

function MapPlan.generate(seed: number)
	if seed ~= seed or math.abs(seed) == math.huge then
		seed = 0
	end
	seed = math.floor(seed)
	local direction = if seed % 2 == 0 then 1 else -1
	local stages = {}
	for index = 1, Rules.StageCount do
		local position = point(index, direction)
		table.insert(stages, {
			X = position.X,
			Y = position.Y,
			Z = position.Z,
			Index = index,
			Size = 8,
			Fragile = index > 2 and index < Rules.StageCount - 1 and (index + seed % 5) % 5 == 0,
		})
	end
	local summit = point(Rules.StageCount + 1, direction)
	return {
		Stages = stages,
		Start = { X = 0, Y = 0, Z = 20, Size = 12 },
		Finish = { X = summit.X, Y = summit.Y, Z = summit.Z, Size = 12 },
		ThemeIndex = seed % 3 + 1,
	}
end

return table.freeze(MapPlan)
