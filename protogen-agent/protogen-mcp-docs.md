# ProtoGen MCP Service Documentation

## Overview

The ProtoGen Model Context Protocol (MCP) service enables AI assistants and language models to interact directly with ProtoGen's manufacturing intelligence platform. This service provides structured access to design optimization, material selection, cost estimation, and manufacturing coordination capabilities.

## MCP Server Configuration

```json
{
  "mcpServers": {
    "protogen": {
      "command": "npx",
      "args": ["-y", "@protogen/mcp-server"],
      "env": {
        "PROTOGEN_API_KEY": "your-api-key",
        "PROTOGEN_ENVIRONMENT": "production"
      }
    }
  }
}
```

## Available Tools

### 1. create_design_project

Creates a new manufacturing project from natural language requirements.

```typescript
{
  "name": "create_design_project",
  "description": "Create a new manufacturing project with design requirements",
  "inputSchema": {
    "type": "object",
    "properties": {
      "name": {
        "type": "string",
        "description": "Project name"
      },
      "description": {
        "type": "string", 
        "description": "Detailed description of what needs to be manufactured"
      },
      "requirements": {
        "type": "object",
        "properties": {
          "function": {
            "type": "string",
            "description": "Primary function or purpose"
          },
          "dimensions": {
            "type": "object",
            "properties": {
              "length": { "type": "number" },
              "width": { "type": "number" },
              "height": { "type": "number" },
              "units": { "type": "string", "enum": ["mm", "cm", "inches"] }
            }
          },
          "constraints": {
            "type": "array",
            "items": { "type": "string" },
            "description": "Design constraints (e.g., 'waterproof', 'heat resistant')"
          },
          "target_cost": {
            "type": "number",
            "description": "Target cost per unit in USD"
          },
          "quantity": {
            "type": "number",
            "description": "Number of units needed"
          }
        }
      }
    },
    "required": ["name", "description"]
  }
}
```

**Example Usage:**
```javascript
await use_mcp_tool("protogen", "create_design_project", {
  name: "Custom Electronics Enclosure",
  description: "Weather-resistant enclosure for IoT sensor with mounting points",
  requirements: {
    function: "Protect electronics from weather while allowing sensor readings",
    dimensions: { length: 120, width: 80, height: 40, units: "mm" },
    constraints: ["IP65 rated", "UV resistant", "Temperature range -20°C to 60°C"],
    target_cost: 15,
    quantity: 100
  }
});
```

### 2. analyze_design_file

Analyzes uploaded CAD files for manufacturability and optimization opportunities.

```typescript
{
  "name": "analyze_design_file",
  "description": "Analyze a CAD file for manufacturability and get recommendations",
  "inputSchema": {
    "type": "object",
    "properties": {
      "project_id": {
        "type": "string",
        "description": "Project ID from create_design_project"
      },
      "file_path": {
        "type": "string",
        "description": "Path to CAD file (STL, STEP, IGES, etc.)"
      },
      "analysis_type": {
        "type": "array",
        "items": {
          "type": "string",
          "enum": ["dfm", "cost", "strength", "weight", "sustainability"]
        },
        "description": "Types of analysis to perform"
      }
    },
    "required": ["project_id", "file_path"]
  }
}
```

### 3. recommend_materials

Get AI-powered material recommendations based on requirements.

```typescript
{
  "name": "recommend_materials",
  "description": "Get material recommendations for a project",
  "inputSchema": {
    "type": "object",
    "properties": {
      "project_id": {
        "type": "string",
        "description": "Project ID"
      },
      "properties_required": {
        "type": "object",
        "properties": {
          "strength": {
            "type": "object",
            "properties": {
              "tensile": { "type": "number", "description": "Tensile strength in MPa" },
              "impact": { "type": "number", "description": "Impact strength in J/m" }
            }
          },
          "temperature": {
            "type": "object",
            "properties": {
              "min": { "type": "number", "description": "Min operating temp °C" },
              "max": { "type": "number", "description": "Max operating temp °C" }
            }
          },
          "chemical_resistance": {
            "type": "array",
            "items": { "type": "string" },
            "description": "Chemicals it must resist"
          },
          "electrical": {
            "type": "string",
            "enum": ["insulator", "conductor", "anti-static"]
          }
        }
      },
      "preferences": {
        "type": "object",
        "properties": {
          "sustainability": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "Importance of sustainability (0-1)"
          },
          "cost_sensitivity": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "Importance of low cost (0-1)"
          }
        }
      }
    },
    "required": ["project_id"]
  }
}
```

### 4. optimize_design

Apply AI-powered optimization to improve the design.

```typescript
{
  "name": "optimize_design",
  "description": "Optimize design for specific goals using AI",
  "inputSchema": {
    "type": "object",
    "properties": {
      "project_id": {
        "type": "string",
        "description": "Project ID"
      },
      "optimization_goals": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "type": {
              "type": "string",
              "enum": ["weight_reduction", "cost_reduction", "strength_increase", 
                       "material_reduction", "assembly_simplification"]
            },
            "target": {
              "type": "number",
              "description": "Target improvement percentage"
            },
            "priority": {
              "type": "number",
              "minimum": 1,
              "maximum": 10,
              "description": "Priority level (1-10)"
            }
          }
        }
      },
      "constraints": {
        "type": "object",
        "properties": {
          "maintain_volume": { "type": "boolean" },
          "preserve_mounting_points": { "type": "boolean" },
          "minimum_wall_thickness": { "type": "number" }
        }
      }
    },
    "required": ["project_id", "optimization_goals"]
  }
}
```

### 5. get_manufacturing_quote

Get real-time quotes from the supplier network.

```typescript
{
  "name": "get_manufacturing_quote",
  "description": "Get manufacturing quotes from suppliers",
  "inputSchema": {
    "type": "object",
    "properties": {
      "project_id": {
        "type": "string",
        "description": "Project ID"
      },
      "material_id": {
        "type": "string",
        "description": "Selected material ID from recommendations"
      },
      "process": {
        "type": "string",
        "enum": ["fdm", "sla", "sls", "mjf", "cnc_milling", "cnc_turning", 
                 "laser_cutting", "injection_molding"],
        "description": "Manufacturing process"
      },
      "quantity": {
        "type": "number",
        "description": "Number of units"
      },
      "deadline": {
        "type": "string",
        "format": "date",
        "description": "Required delivery date"
      },
      "location": {
        "type": "object",
        "properties": {
          "country": { "type": "string" },
          "state": { "type": "string" },
          "postal_code": { "type": "string" }
        },
        "description": "Delivery location for shipping estimates"
      },
      "certifications_required": {
        "type": "array",
        "items": {
          "type": "string",
          "enum": ["ISO9001", "AS9100", "ISO13485", "ITAR", "FDA"]
        }
      }
    },
    "required": ["project_id", "material_id", "process", "quantity"]
  }
}
```

### 6. simulate_performance

Run engineering simulations on the design.

```typescript
{
  "name": "simulate_performance",
  "description": "Run FEA/CFD simulations on design",
  "inputSchema": {
    "type": "object",
    "properties": {
      "project_id": {
        "type": "string",
        "description": "Project ID"
      },
      "simulation_type": {
        "type": "string",
        "enum": ["static_stress", "thermal", "flow", "modal", "fatigue"],
        "description": "Type of simulation to run"
      },
      "loading_conditions": {
        "type": "object",
        "properties": {
          "forces": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "location": { "type": "string" },
                "magnitude": { "type": "number" },
                "direction": { "type": "array", "items": { "type": "number" } }
              }
            }
          },
          "constraints": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "location": { "type": "string" },
                "type": { "type": "string", "enum": ["fixed", "pinned", "sliding"] }
              }
            }
          }
        }
      },
      "material_properties": {
        "type": "object",
        "description": "Override material properties if needed"
      }
    },
    "required": ["project_id", "simulation_type"]
  }
}
```

### 7. place_manufacturing_order

Place an order with a selected supplier.

```typescript
{
  "name": "place_manufacturing_order",
  "description": "Place manufacturing order with supplier",
  "inputSchema": {
    "type": "object",
    "properties": {
      "project_id": {
        "type": "string",
        "description": "Project ID"
      },
      "quote_id": {
        "type": "string",
        "description": "Selected quote ID"
      },
      "shipping_address": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "company": { "type": "string" },
          "address_line_1": { "type": "string" },
          "address_line_2": { "type": "string" },
          "city": { "type": "string" },
          "state": { "type": "string" },
          "postal_code": { "type": "string" },
          "country": { "type": "string" },
          "phone": { "type": "string" }
        },
        "required": ["name", "address_line_1", "city", "state", "postal_code", "country"]
      },
      "payment_method": {
        "type": "object",
        "properties": {
          "type": { "type": "string", "enum": ["credit_card", "po", "wire"] },
          "details": { "type": "object" }
        }
      },
      "special_instructions": {
        "type": "string",
        "description": "Any special manufacturing or shipping instructions"
      }
    },
    "required": ["project_id", "quote_id", "shipping_address"]
  }
}
```

### 8. track_order_status

Get real-time manufacturing and shipping status.

```typescript
{
  "name": "track_order_status",
  "description": "Track manufacturing order status",
  "inputSchema": {
    "type": "object",
    "properties": {
      "order_id": {
        "type": "string",
        "description": "Order ID from place_manufacturing_order"
      },
      "include_photos": {
        "type": "boolean",
        "description": "Include progress photos if available"
      }
    },
    "required": ["order_id"]
  }
}
```

## Resources

### 1. Material Database Access

```typescript
{
  "uri": "protogen://materials",
  "name": "ProtoGen Material Database",
  "description": "Access to 5000+ materials with properties and pricing",
  "mimeType": "application/json"
}
```

### 2. Design Templates

```typescript
{
  "uri": "protogen://templates/{category}",
  "name": "Design Template Library",
  "description": "Parametric design templates by category",
  "mimeType": "application/json"
}
```

### 3. Supplier Network

```typescript
{
  "uri": "protogen://suppliers",
  "name": "Supplier Network Directory",
  "description": "Verified manufacturing suppliers with capabilities",
  "mimeType": "application/json"
}
```

## Example Workflows

### Complete Project Workflow

```javascript
// 1. Create project from description
const project = await use_mcp_tool("protogen", "create_design_project", {
  name: "Drone Frame",
  description: "Lightweight frame for racing drone with motor mounts",
  requirements: {
    function: "Support 4 motors and flight controller",
    dimensions: { length: 250, width: 250, height: 50, units: "mm" },
    constraints: ["weight under 200g", "vibration resistant"],
    target_cost: 25,
    quantity: 50
  }
});

// 2. Analyze uploaded design
const analysis = await use_mcp_tool("protogen", "analyze_design_file", {
  project_id: project.id,
  file_path: "/uploads/drone_frame_v1.stl",
  analysis_type: ["dfm", "weight", "strength"]
});

// 3. Get material recommendations
const materials = await use_mcp_tool("protogen", "recommend_materials", {
  project_id: project.id,
  properties_required: {
    strength: { tensile: 50 },
    temperature: { min: -10, max: 60 }
  },
  preferences: {
    sustainability: 0.3,
    cost_sensitivity: 0.8
  }
});

// 4. Optimize design
const optimized = await use_mcp_tool("protogen", "optimize_design", {
  project_id: project.id,
  optimization_goals: [
    { type: "weight_reduction", target: 20, priority: 10 },
    { type: "cost_reduction", target: 15, priority: 7 }
  ],
  constraints: {
    maintain_volume: false,
    preserve_mounting_points: true,
    minimum_wall_thickness: 1.5
  }
});

// 5. Get quotes
const quotes = await use_mcp_tool("protogen", "get_manufacturing_quote", {
  project_id: project.id,
  material_id: materials.recommendations[0].material_id,
  process: "fdm",
  quantity: 50,
  deadline: "2025-09-15",
  location: {
    country: "US",
    state: "CA",
    postal_code: "94025"
  }
});

// 6. Place order
const order = await use_mcp_tool("protogen", "place_manufacturing_order", {
  project_id: project.id,
  quote_id: quotes.quotes[0].quote_id,
  shipping_address: {
    name: "John Doe",
    company: "Drone Racing Inc",
    address_line_1: "123 Main St",
    city: "Menlo Park",
    state: "CA",
    postal_code: "94025",
    country: "US",
    phone: "+1-555-0123"
  }
});

// 7. Track order
const status = await use_mcp_tool("protogen", "track_order_status", {
  order_id: order.order_id,
  include_photos: true
});
```

### Quick Cost Estimation

```javascript
// Get quick cost estimate for a simple part
const project = await use_mcp_tool("protogen", "create_design_project", {
  name: "Quick Bracket",
  description: "L-shaped bracket, 50x50x3mm"
});

const quotes = await use_mcp_tool("protogen", "get_manufacturing_quote", {
  project_id: project.id,
  material_id: "abs_standard",
  process: "fdm",
  quantity: 10
});

console.log(`Cost: $${quotes.quotes[0].unit_cost} each`);
```

## Error Handling

All tools return structured error responses:

```json
{
  "error": {
    "type": "validation_error|authentication_error|processing_error|quota_exceeded",
    "message": "Human-readable error message",
    "details": {
      "field": "specific field that caused error",
      "suggestion": "How to fix the error"
    }
  }
}
```

## Rate Limits

- **Design Analysis**: 100 requests/hour
- **Optimization**: 20 requests/hour
- **Quote Generation**: 200 requests/hour
- **Order Placement**: 50 requests/hour

## Authentication

The MCP server handles authentication automatically using the API key provided in the configuration. Each API key is associated with:

- Organization/user account
- Subscription tier
- Available features
- Rate limits
- Billing information

## Best Practices

1. **Project Reuse**: Store project IDs to avoid recreating projects for iterations
2. **Batch Operations**: Combine multiple analyses in single requests when possible
3. **Caching**: Quote results are cached for 24 hours
4. **File Formats**: Use STEP files for best compatibility
5. **Material Selection**: Always run recommendations before selecting materials
6. **Optimization**: Start with single optimization goals before combining multiple

## Support

- **Documentation**: https://docs.protogen.ai/mcp
- **API Status**: https://status.protogen.ai
- **Support Email**: mcp-support@protogen.ai
- **Discord Community**: https://discord.gg/protogen