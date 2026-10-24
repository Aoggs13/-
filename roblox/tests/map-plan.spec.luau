local MapPlan = require("../src/shared/MapPlan")
local Rules = require("../src/shared/Rules")

local tests = 0
local function test(name, run)
	run()
	tests += 1
	print("PASS " .. name)
end

local function near(a, b)
	assert(math.abs(a - b) < 1e-9, string.format("%s differs from %s", tostring(a), tostring(b)))
end

test("same seed produces the same complete route", function()
	local a, b = MapPlan.generate(42), MapPlan.generate(42)
	assert(a.ThemeIndex == b.ThemeIndex)
	for i, stage in a.Stages do
		for key, value in stage do
			assert(value == b.Stages[i][key])
		end
	end
end)

test("seed changes direction, theme, and fragile positions", function()
	local a, b = MapPlan.generate(0), MapPlan.generate(1)
	assert(a.ThemeIndex ~= b.ThemeIndex)
	for i, stage in a.Stages do
		near(stage.X, -b.Stages[i].X)
		near(stage.Y, b.Stages[i].Y)
		near(stage.Z, b.Stages[i].Z)
	end
	assert(a.Stages[4].Fragile ~= b.Stages[4].Fragile)
end)

test("every route has 24 finite distinct stages and a reachable summit", function()
	for seed = -12, 30 do
		local map = MapPlan.generate(seed)
		assert(#map.Stages == Rules.StageCount)
		assert(map.ThemeIndex >= 1 and map.ThemeIndex <= 3)
		local previous = map.Start
		local route = table.clone(map.Stages)
		table.insert(route, map.Finish)
		for i, stage in route do
			for _, coordinate in { stage.X, stage.Y, stage.Z } do
				assert(coordinate == coordinate and math.abs(coordinate) < math.huge)
			end
			-- Squares are axis aligned, so center distance minus their half widths
			-- conservatively overestimates the actual horizontal gap.
			local distance = math.sqrt((stage.X - previous.X) ^ 2 + (stage.Z - previous.Z) ^ 2)
			local gap = distance - (stage.Size + previous.Size) / 2
			assert(gap <= 4, "jump exceeds conservative horizontal gap")
			assert(stage.Y > previous.Y and stage.Y - previous.Y <= Rules.StageRise + 1e-9)
			if i <= Rules.StageCount then
				assert(stage.Index == i)
			end
			previous = stage
		end
		near(map.Finish.Y, 90)
		assert(map.Finish.Y > Rules.LavaEnd)
	end
end)

test("fragile platforms never appear next to each other or at route ends", function()
	for seed = 0, 60 do
		local stages = MapPlan.generate(seed).Stages
		assert(not stages[1].Fragile and not stages[#stages].Fragile)
		local fragile = 0
		for i, stage in stages do
			if stage.Fragile then
				fragile += 1
				assert(not stages[i - 1].Fragile and not stages[i + 1].Fragile)
			end
		end
		assert(fragile >= 3 and fragile <= 5)
	end
end)

test("invalid seeds still generate finite repeatable geometry", function()
	for _, seed in { 0 / 0, math.huge, -math.huge } do
		local map = MapPlan.generate(seed)
		assert(map.ThemeIndex == 1)
		near(map.Stages[1].X, MapPlan.generate(0).Stages[1].X)
	end
end)

print(string.format("MapPlan: %d tests passed", tests))
