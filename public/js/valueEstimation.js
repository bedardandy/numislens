// Value Estimation Algorithm for Numislens
// Estimates coin values based on grade, rarity, and other factors without using a pricing API

class ValueEstimationSystem {
    constructor() {
        // Base values for different coin types (in USD)
        this.baseValues = {
            // US Cents
            'Lincoln Memorial Penny': 0.01,
            'Wheat Penny': 0.05,
            'Lincoln Cent (1909-1958)': 0.10,
            
            // US Nickels
            'Buffalo Nickel': 1.00,
            'Jefferson Nickel': 0.05,
            'Shield Nickel': 2.00,
            
            // US Dimes
            'Mercury Dime': 3.00,
            'Roosevelt Dime': 0.10,
            'Barber Dime': 3.00,
            
            // US Quarters
            'Standing Liberty Quarter': 5.00,
            'Washington Quarter': 0.25,
            'Barber Quarter': 8.00,
            
            // US Half Dollars
            'Walking Liberty Half Dollar': 12.00,
            'Franklin Half Dollar': 2.00,
            'Kennedy Half Dollar': 0.50,
            'Barber Half Dollar': 15.00,
            
            // US Dollars
            'Morgan Silver Dollar': 20.00,
            'Peace Silver Dollar': 18.00,
            'Eisenhower Dollar': 1.00,
            'Sacagawea Dollar': 1.00,
            'Presidential Dollar': 1.00,
            
            // Commemorative & Special Issues
            'Commemorative Coin': 5.00,
            'Proof Coin': 10.00,
            'Error Coin': 25.00
        };
        
        // Grade multipliers - how much the grade affects value
        this.gradeMultipliers = {
            'MS-70': 100.0,  // Perfect mint state
            'MS-69': 85.0,
            'MS-68': 70.0,
            'MS-67': 60.0,
            'MS-66': 50.0,
            'MS-65': 40.0,   // Brilliant uncirculated
            'MS-64': 30.0,
            'MS-63': 25.0,   // Choice uncirculated
            'MS-62': 20.0,
            'MS-61': 18.0,
            'MS-60': 15.0,   // Uncirculated
            'AU-58': 12.0,
            'AU-55': 10.0,   // About uncirculated
            'AU-53': 8.0,
            'AU-50': 7.0,
            'XF-45': 6.0,    // Extremely fine
            'XF-40': 5.0,
            'VF-35': 4.0,    // Very fine
            'VF-30': 3.5,
            'VF-25': 3.0,
            'VF-20': 2.5,
            'F-15': 2.0,     // Fine
            'F-12': 1.8,
            'VG-10': 1.5,    // Very good
            'VG-8': 1.3,
            'G-6': 1.2,      // Good
            'G-4': 1.1,
            'AG-3': 1.0      // About good
        };
        
        // Rarity multipliers based on mintage and survival
        this.rarityMultipliers = {
            'common': 1.0,      // High mintage, many survive
            'semi_common': 1.5, // Moderate mintage
            'scarce': 3.0,      // Lower mintage
            'rare': 8.0,        // Very low mintage
            'very_rare': 20.0,  // Extremely low mintage
            'extremely_rare': 50.0, // Exceptionally rare
            'unique': 100.0     // Only one known to exist
        };
        
        // Composition multipliers (for precious metals)
        this.compositionMultipliers = {
            'copper': 1.0,
            'copper_plated_zinc': 1.0,
            'copper_nickel': 1.0,
            'silver_40': 2.0,   // 40% silver
            'silver_90': 5.0,   // 90% silver
            'silver_999': 8.0,  // 99.9% silver
            'gold': 25.0,       // Gold content
            'platinum': 40.0    // Platinum content
        };
        
        // Year-based multipliers for historically significant years
        this.yearMultipliers = {
            // Key dates that are worth more regardless of grade
            1909: 3.0,    // First Lincoln cents
            1909S: 15.0,  // 1909-S VDB Lincoln cent
            1914D: 8.0,   // 1914-D Lincoln cent
            1922: 5.0,    // 1922 Plain (no mintmark) cent
            1932S: 12.0,  // 1932-S Washington quarter
            1955: 25.0,   // 1955 Doubled Die Obverse cent
            1969S: 15.0,  // 1969-S Lincoln cent (doubled die)
            1970S: 3.0,   // 1970-S Jefferson nickel (no mintmark after 1966)
            1983: 2.0,    // 1983-P Washington quarter (error coins)
            
            // Morgan dollars
            1921: 2.0,    // Last year of Morgan dollars
            1921PL: 3.0,  // Peace dollar first year
            1893S: 50.0,  // Key date Morgan dollar
            1901: 15.0,   // High relief Saint-Gaudens
        };
        
        // Condition adjustment factors
        this.conditionAdjustments = {
            // Adjustments for specific condition issues
            cleaning: 0.3,      // Cleaned coins are worth much less
            scratches: 0.7,     // Surface scratches
            dents: 0.8,         // Dents or dings
            edge_nicks: 0.9,    // Edge nicks
            no_issues: 1.0      // No significant issues
        };
    }
    
    // Main method to estimate coin value
    estimateValue(coinData) {
        try {
            // Extract relevant data from coin identification
            const {
                name,
                year,
                mintmark,
                grade,
                composition,
                denomination,
                country,
                rarity
            } = coinData;
            
            // Calculate base value based on coin type
            const baseValue = this.calculateBaseValue(name, denomination);
            
            // Apply grade multiplier
            const gradeMultiplier = this.getGradeMultiplier(grade);
            
            // Apply rarity multiplier
            const rarityMultiplier = this.getRarityMultiplier(rarity);
            
            // Apply composition multiplier (for precious metals)
            const compositionMultiplier = this.getCompositionMultiplier(composition);
            
            // Apply year-specific multiplier for key dates
            const yearMultiplier = this.getYearMultiplier(year, mintmark);
            
            // Calculate preliminary value
            let preliminaryValue = baseValue * gradeMultiplier * rarityMultiplier * 
                                 compositionMultiplier * yearMultiplier;
            
            // Apply condition adjustments if available
            const conditionAdjustment = coinData.conditionAdjustments || this.conditionAdjustments.no_issues;
            const finalValue = preliminaryValue * conditionAdjustment;
            
            // Calculate value range (typical spread in numismatics)
            const valueRange = this.calculateValueRange(finalValue, grade, rarity);
            
            return {
                estimatedValue: finalValue,
                valueRange: valueRange,
                breakdown: {
                    baseValue: baseValue,
                    gradeMultiplier: gradeMultiplier,
                    rarityMultiplier: rarityMultiplier,
                    compositionMultiplier: compositionMultiplier,
                    yearMultiplier: yearMultiplier,
                    conditionAdjustment: conditionAdjustment
                },
                confidence: this.calculateConfidence(grade, rarity, composition)
            };
            
        } catch (error) {
            console.error('Value estimation error:', error);
            // Return a safe fallback value
            return {
                estimatedValue: 0,
                valueRange: { min: 0, max: 0 },
                breakdown: {},
                confidence: 0
            };
        }
    }
    
    // Calculate base value based on coin name and denomination
    calculateBaseValue(name, denomination) {
        // Try to match the coin name to our base values
        for (const [coinType, value] of Object.entries(this.baseValues)) {
            if (name.includes(coinType)) {
                return value;
            }
        }
        
        // If no exact match, try to determine from denomination
        if (denomination) {
            const denom = denomination.toLowerCase();
            if (denom.includes('cent') || denom.includes('penny')) return 0.05;
            if (denom.includes('nickel')) return 0.10;
            if (denom.includes('dime')) return 0.25;
            if (denom.includes('quarter')) return 0.50;
            if (denom.includes('half') && denom.includes('dollar')) return 2.00;
            if (denom.includes('dollar')) return 1.00;
        }
        
        // Default fallback value
        return 1.00;
    }
    
    // Get grade multiplier
    getGradeMultiplier(grade) {
        if (!grade) return 1.0;
        
        // Handle grades that might have additional descriptors
        const cleanGrade = grade.trim().toUpperCase();
        
        // Check for exact match first
        if (this.gradeMultipliers[cleanGrade]) {
            return this.gradeMultipliers[cleanGrade];
        }
        
        // If not found, try to match the grade prefix (e.g., MS-65 -> MS)
        const gradePrefix = cleanGrade.substring(0, 2);
        for (const [gradeKey, multiplier] of Object.entries(this.gradeMultipliers)) {
            if (gradeKey.startsWith(gradePrefix)) {
                // Return the highest multiplier for that grade category
                return multiplier;
            }
        }
        
        // Default multiplier for unknown grades
        return 1.0;
    }
    
    // Get rarity multiplier
    getRarityMultiplier(rarity) {
        if (!rarity) return 1.0;
        
        const rarityKey = rarity.toLowerCase();
        if (this.rarityMultipliers[rarityKey]) {
            return this.rarityMultipliers[rarityKey];
        }
        
        // Default for unknown rarity
        return 1.0;
    }
    
    // Get composition multiplier
    getCompositionMultiplier(composition) {
        if (!composition) return 1.0;
        
        const comp = composition.toLowerCase();
        
        // Check for silver content
        if (comp.includes('silver')) {
            if (comp.includes('90') || comp.includes('99')) {
                return this.compositionMultipliers.silver_90;
            } else if (comp.includes('40')) {
                return this.compositionMultipliers.silver_40;
            }
            return this.compositionMultipliers.silver_90; // Default silver
        }
        
        // Check for gold content
        if (comp.includes('gold')) {
            return this.compositionMultipliers.gold;
        }
        
        // Check for platinum
        if (comp.includes('platinum')) {
            return this.compositionMultipliers.platinum;
        }
        
        // Default for base metals
        return 1.0;
    }
    
    // Get year multiplier for key dates
    getYearMultiplier(year, mintmark) {
        if (!year) return 1.0;
        
        // Create key for year + mintmark combination
        const yearMintKey = `${year}${mintmark || ''}`;
        
        // Check for specific year+mintmark combinations first
        if (this.yearMultipliers[yearMintKey]) {
            return this.yearMultipliers[yearMintKey];
        }
        
        // Check for year only
        if (this.yearMultipliers[year]) {
            return this.yearMultipliers[year];
        }
        
        // For years before 1965 (generally more valuable due to silver content)
        if (year < 1965) {
            return 1.5; // Pre-1965 coins often have higher value
        }
        
        // Default multiplier
        return 1.0;
    }
    
    // Calculate value range based on market volatility
    calculateValueRange(baseValue, grade, rarity) {
        // Value ranges vary based on grade and rarity
        let minMultiplier, maxMultiplier;
        
        if (rarity === 'extremely_rare' || rarity === 'unique') {
            // Extremely rare coins have wide value ranges
            minMultiplier = 0.5;
            maxMultiplier = 3.0;
        } else if (grade && (grade.startsWith('MS') || grade.startsWith('AU'))) {
            // Higher grade coins have more defined values
            minMultiplier = 0.7;
            maxMultiplier = 1.5;
        } else {
            // Lower grade coins have moderate ranges
            minMultiplier = 0.6;
            maxMultiplier = 1.8;
        }
        
        return {
            min: Math.max(0.01, baseValue * minMultiplier),
            max: baseValue * maxMultiplier
        };
    }
    
    // Calculate confidence in the estimate
    calculateConfidence(grade, rarity, composition) {
        // Confidence is based on how well we can estimate value
        let confidence = 50; // Base confidence
        
        // Higher grades generally have more predictable values
        if (grade && (grade.startsWith('MS') || grade.startsWith('AU'))) {
            confidence += 20;
        }
        
        // Known rarities increase confidence
        if (rarity) {
            confidence += 15;
        }
        
        // Precious metal compositions are more predictable
        if (composition && (composition.toLowerCase().includes('silver') || 
                           composition.toLowerCase().includes('gold'))) {
            confidence += 10;
        }
        
        // Cap at 95% (never 100% confident in numismatics)
        return Math.min(95, confidence);
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ValueEstimationSystem;
} else {
    // For browser environment
    window.ValueEstimationSystem = ValueEstimationSystem;
}