-- parody-twinmarks: at each shipout, record which mark values sit on how many
-- lines of the page. Output, one row per (page, value) present:
--   abspage <TAB> page number <TAB> value <TAB> lines
-- A "line" is a paragraph line or a display (hlist subtypes 1, 6, 7) holding
-- the value in any leaf; a value can also be present with 0 lines (an image).
local attr = luatexbase.registernumber("parodytwinattr")
local HLIST, VLIST = node.id("hlist"), node.id("vlist")
local GLYPH, RULE, WHATSIT = node.id("glyph"), node.id("rule"), node.id("whatsit")
local out = io.open(tex.jobname .. ".twin", "w")
local abspage = 0

local function leaves(head, seen)
  for m in node.traverse(head) do
    if m.id == HLIST or m.id == VLIST then
      if m.list then leaves(m.list, seen) end
    elseif m.id == GLYPH or m.id == RULE or m.id == WHATSIT then
      local v = node.has_attribute(m, attr)
      if v and v > 0 then seen[v] = true end
    end
  end
end

local function is_line(m)
  return m.id == HLIST and (m.subtype == 1 or m.subtype == 6 or m.subtype == 7)
end

-- A box set in a paragraph (a breakable definition box, say) is itself a
-- "line" holding many lines: count those, not the box.
local function holds_lines(head)
  for m in node.traverse(head) do
    if is_line(m) then return true end
    if (m.id == HLIST or m.id == VLIST) and m.list and holds_lines(m.list) then return true end
  end
  return false
end

local function rows(head, counts)
  for m in node.traverse(head) do
    if is_line(m) and not (m.list and holds_lines(m.list)) then
      local seen = {}
      if m.list then leaves(m.list, seen) end
      for v in pairs(seen) do counts[v] = (counts[v] or 0) + 1 end
    elseif (m.id == HLIST or m.id == VLIST) and m.list then
      rows(m.list, counts)
    end
  end
end

luatexbase.add_to_callback("pre_shipout_filter", function(head)
  abspage = abspage + 1
  local counts, present = {}, {}
  rows(head, counts)
  leaves(head, present)
  local values = {}
  for v in pairs(present) do values[#values + 1] = v end
  table.sort(values)
  for _, v in ipairs(values) do
    out:write(string.format("%d\t%d\t%d\t%d\n", abspage, tex.count["c@page"], v, counts[v] or 0))
  end
  out:flush()
  return head
end, "parodytwinmarks")
