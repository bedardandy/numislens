-- The 1943 Lincoln "steel cent" (zinc-coated steel) is the only regular-issue
-- U.S. steel cent, so the phrase "steel cent" names the metal unambiguously.
-- This composition backs the quick-add certain-composition rule for steel cents.
-- Base metal (no precious content): metal / fineness / precious_weight_ozt are
-- NULL, so it contributes zero melt and never fabricates a bullion value.
INSERT OR IGNORE INTO compositions (name, metal, fineness, precious_weight_ozt, nominal_weight_g, notes)
VALUES ('Steel cent', NULL, NULL, NULL, 2.7, 'Zinc-coated steel; 1943 Lincoln wheat cent (WWII copper conservation)');
