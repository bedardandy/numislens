// Coin Grading System for Numislens
// Evaluates coin condition and assigns a grade according to standard numismatic scales

class CoinGradingSystem {
    constructor() {
        // Grading scales used in numismatics
        this.gradingScales = {
            // Sheldon Scale (used primarily for US coins)
            sheldonScale: {
                'MS-70': { name: 'Mint State 70', description: 'Perfect coin with no flaws, full original luster' },
                'MS-69': { name: 'Mint State 69', description: 'Nearly perfect, minuscule flaws only under magnification' },
                'MS-65': { name: 'Mint State 65', description: 'Brilliant original luster with only minor contact marks' },
                'MS-63': { name: 'Mint State 63', description: 'Moderate luster, few small contact marks, no major detracting flaws' },
                'AU-58': { name: 'About Uncirculated 58', description: 'Light friction in high points, nearly full original luster' },
                'AU-55': { name: 'About Uncirculated 55', description: 'Some friction on high points, considerable original luster' },
                'AU-50': { name: 'About Uncirculated 50', description: 'Definite wear on high points, some original luster' },
                'XF-45': { name: 'Extremely Fine 45', description: 'Light wear on high points, sharp design details' },
                'XF-40': { name: 'Extremely Fine 40', description: 'Light wear on high points, all design details sharp' },
                'VF-30': { name: 'Very Fine 30', description: 'Even wear on surface, design elements clear and bold' },
                'VF-20': { name: 'Very Fine 20', description: 'Moderate wear on high points, clear design details' },
                'F-12': { name: 'Fine 12', description: 'Even wear, major design elements clear, readable date' },
                'VG-8': { name: 'Very Good 8', description: 'Even moderate wear, all lettering clear, major design visible' },
                'G-4': { name: 'Good 4', description: 'Heavy even wear, design outline visible, date readable' },
                'AG-3': { name: 'About Good 3', description: 'Heavily worn, design barely visible, date barely readable' }
            }
        };
        
        // Condition factors that affect grading
        this.conditionFactors = {
            wear: {
                weight: 0.4, // 40% of grade
                description: 'Amount of wear on the coin\'s surface and design elements'
            },
            luster: {
                weight: 0.2, // 20% of grade
                description: 'Original mint shine and reflectivity'
            },
            strike: {
                weight: 0.15, // 15% of grade
                description: 'How well the design was impressed into the metal'
            },
            surface: {
                weight: 0.15, // 15% of grade
                description: 'Quality of the coin\'s surface, including marks and scratches'
            },
            eyeAppeal: {
                weight: 0.1 // 10% of grade
                description: 'Overall visual attractiveness of the coin'
            }
        };
    }
    
    // Main grading function that takes image analysis results and other factors
    gradeCoin(coinAnalysis, imageQuality, conditionFactors) {
        // Calculate base grade based on condition factors
        const baseGrade = this.calculateBaseGrade(conditionFactors);
        
        // Adjust grade based on image quality (affects how well we can assess condition)
        const adjustedGrade = this.adjustForImageQuality(baseGrade, imageQuality);
        
        // Get the appropriate grade based on the calculated score
        const grade = this.mapScoreToGrade(adjustedGrade);
        
        return {
            grade: grade,
            score: adjustedGrade,
            factors: conditionFactors,
            confidence: this.calculateConfidence(conditionFactors, imageQuality)
        };
    }
    
    // Calculate base grade score from condition factors (0-100 scale)
    calculateBaseGrade(factors) {
        let totalScore = 0;
        
        for (const [factor, value] of Object.entries(factors)) {
            if (this.conditionFactors[factor]) {
                // Convert factor value (0-10 scale) to 0-100, then apply weight
                const factorScore = value * 10; // Convert 0-10 to 0-100
                totalScore += factorScore * this.conditionFactors[factor].weight;
            }
        }
        
        return Math.round(totalScore);
    }
    
    // Adjust grade based on image quality (0-10 scale)
    adjustForImageQuality(baseScore, imageQuality) {
        // If image quality is poor, reduce confidence in grading
        const qualityAdjustment = (imageQuality / 10) * 0.8 + 0.2; // 0.2 to 1.0 multiplier
        return Math.round(baseScore * qualityAdjustment);
    }
    
    // Map numerical score to standard grade
    mapScoreToGrade(score) {
        // Convert 0-100 score to grading scale
        if (score >= 95) return 'MS-70';
        if (score >= 93) return 'MS-69';
        if (score >= 88) return 'MS-65';
        if (score >= 83) return 'MS-63';
        if (score >= 78) return 'AU-58';
        if (score >= 73) return 'AU-55';
        if (score >= 68) return 'AU-50';
        if (score >= 63) return 'XF-45';
        if (score >= 58) return 'XF-40';
        if (score >= 50) return 'VF-30';
        if (score >= 40) return 'VF-20';
        if (score >= 25) return 'F-12';
        if (score >= 15) return 'VG-8';
        if (score >= 8) return 'G-4';
        return 'AG-3';
    }
    
    // Calculate confidence in the grade (0-100%)
    calculateConfidence(factors, imageQuality) {
        // Confidence is based on completeness of factor assessment and image quality
        const factorCount = Object.keys(factors).length;
        const maxFactors = Object.keys(this.conditionFactors).length;
        const factorCompleteness = factorCount / maxFactors;
        
        // Combine factor completeness and image quality for overall confidence
        const confidence = (factorCompleteness * 0.6 + (imageQuality / 10) * 0.4) * 100;
        
        return Math.round(confidence);
    }
    
    // Get grade description
    getGradeDescription(grade) {
        return this.gradingScales.sheldonScale[grade]?.description || 'Unknown grade';
    }
    
    // Analyze coin condition from image data (simplified for this implementation)
    analyzeConditionFromImage(imageData) {
        // In a real implementation, this would analyze the image for:
        // - Wear patterns
        // - Surface marks
        // - Luster preservation
        // - Strike quality
        
        // For this demo, we'll return simulated values based on common patterns
        return {
            wear: this.estimateWearLevel(imageData),
            luster: this.estimateLusterLevel(imageData),
            strike: this.estimateStrikeQuality(imageData),
            surface: this.estimateSurfaceQuality(imageData),
            eyeAppeal: this.estimateEyeAppeal(imageData)
        };
    }
    
    // Helper methods to estimate condition factors from image data
    estimateWearLevel(imageData) {
        // In a real implementation, this would analyze high points of the design for wear
        // For demo, return a random value between 1-10 based on common wear patterns
        return Math.floor(Math.random() * 4) + 6; // 6-9 (good to excellent)
    }
    
    estimateLusterLevel(imageData) {
        // In a real implementation, this would analyze reflectivity and shine
        return Math.floor(Math.random() * 5) + 5; // 5-9 (moderate to excellent)
    }
    
    estimateStrikeQuality(imageData) {
        // In a real implementation, this would analyze how well design details are impressed
        return Math.floor(Math.random() * 4) + 6; // 6-9 (good to excellent)
    }
    
    estimateSurfaceQuality(imageData) {
        // In a real implementation, this would look for scratches, marks, etc.
        return Math.floor(Math.random() * 5) + 5; // 5-9 (moderate to excellent)
    }
    
    estimateEyeAppeal(imageData) {
        // In a real implementation, this would assess overall visual attractiveness
        return Math.floor(Math.random() * 4) + 6; // 6-9 (good to excellent)
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CoinGradingSystem;
} else {
    // For browser environment
    window.CoinGradingSystem = CoinGradingSystem;
}