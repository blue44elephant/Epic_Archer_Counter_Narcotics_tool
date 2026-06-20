# Epic Archer - Complete Documentation Index

**Version**: 1.0.0  
**Last Updated**: June 21, 2026  
**Project**: Epic Archer Counter-Narcotics Intelligence Tool

---

## 📋 Documentation Overview

Epic Archer documentation is organized by audience and use case. Use this index to find what you need.

---

## 👤 By Role

### For End Users / Operations

**You want to**: Install the tool and use it for maritime surveillance

1. **[README.md](README.md)** — START HERE
   - Features overview
   - 5-minute quick start
   - Environment setup
   - Docker or local deployment
   - Using the application & dashboard

2. **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)**
   - Common problems and solutions
   - Connection issues
   - Docker troubleshooting
   - Dark ship detection issues

### For System Administrators / DevOps

**You want to**: Deploy, configure, and maintain Epic Archer

1. **[DOCKER_DEPLOY.md](DOCKER_DEPLOY.md)** — Extended Docker guide
   - Detailed deployment steps
   - Configuration management
   - Container orchestration
   - Health monitoring

2. **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)**
   - Docker-specific issues
   - Network configuration
   - Database maintenance
   - Performance tuning

3. **[DATABASE.md](DATABASE.md)**
   - Backup and recovery
   - Database optimization
   - Maintenance operations
   - Scaling considerations

### For Developers / Contributors

**You want to**: Understand the codebase and make changes

1. **[DEVELOPMENT.md](DEVELOPMENT.md)** — START HERE
   - Local dev environment setup
   - Code structure and conventions
   - Common development tasks
   - Testing & debugging
   - Git workflow

2. **[ARCHITECTURE.md](ARCHITECTURE.md)**
   - System design and components
   - Data flow diagrams
   - Module interactions
   - External integrations
   - Performance characteristics

3. **[DATABASE.md](DATABASE.md)**
   - Database schema details
   - Query patterns
   - Performance optimization
   - Common queries

### For API Consumers / Integrators

**You want to**: Use Epic Archer's APIs in your application

1. **[API_DOCUMENTATION.md](API_DOCUMENTATION.md)** — START HERE
   - Complete API reference
   - Dark ships endpoints
   - Real-time data endpoints
   - Request/response formats
   - Error handling
   - Usage examples in multiple languages

### For Software Architects

**You want to**: Understand the overall system design

1. **[ARCHITECTURE.md](ARCHITECTURE.md)** — START HERE
   - System overview & diagrams
   - Component descriptions
   - Data flow & interactions
   - Integration points
   - Scalability & performance
   - Security considerations
   - Future enhancements

2. **[DATABASE.md](DATABASE.md)**
   - Data models
   - Schema design
   - Indexing strategy
   - Migration path

---

## 📚 By Topic

### Getting Started

1. **[README.md](README.md)#getting-started** — Quick start (5 min)
2. **[DOCKER_DEPLOY.md](DOCKER_DEPLOY.md)#quick-start** — Docker quick start
3. **[DEVELOPMENT.md](DEVELOPMENT.md)#development-setup** — Dev setup

### Installation & Deployment

- **Local**: [README.md](README.md#option-b-local-deployment-development)
- **Docker**: [DOCKER_DEPLOY.md](DOCKER_DEPLOY.md) or [README.md](README.md#option-a-docker-deployment)
- **Configuration**: [README.md](README.md#step-2-configure-environment-variables)
- **API Keys**: [README.md](README.md#step-1-get-your-api-keys)

### API & Integration

- **Full API Reference**: [API_DOCUMENTATION.md](API_DOCUMENTATION.md)
- **Dark Ships API**: [API_DOCUMENTATION.md](API_DOCUMENTATION.md#dark-ships-api-endpoints-new)
- **Real-time Data**: [API_DOCUMENTATION.md](API_DOCUMENTATION.md#real-time-data-endpoints)
- **Examples**: [API_DOCUMENTATION.md](API_DOCUMENTATION.md#usage-examples)

### Database

- **Schema**: [DATABASE.md](DATABASE.md#database-schema)
- **Tables**: [DATABASE.md](DATABASE.md#table-1-dark_ship_events)
- **Queries**: [DATABASE.md](DATABASE.md#common-queries)
- **Maintenance**: [DATABASE.md](DATABASE.md#maintenance-operations)
- **Troubleshooting**: [DATABASE.md](DATABASE.md#troubleshooting) or [TROUBLESHOOTING.md](TROUBLESHOOTING.md#database-issues)

### Architecture & Design

- **System Overview**: [ARCHITECTURE.md](ARCHITECTURE.md#overview)
- **Components**: [ARCHITECTURE.md](ARCHITECTURE.md#core-components)
- **Data Flows**: [ARCHITECTURE.md](ARCHITECTURE.md#data-flow-diagrams)
- **Performance**: [ARCHITECTURE.md](ARCHITECTURE.md#performance-characteristics)
- **Security**: [ARCHITECTURE.md](ARCHITECTURE.md#security-architecture)
- **External Services**: [ARCHITECTURE.md](ARCHITECTURE.md#external-service-integrations)

### Development

- **Setup**: [DEVELOPMENT.md](DEVELOPMENT.md#development-setup)
- **Code Style**: [DEVELOPMENT.md](DEVELOPMENT.md#code-style--conventions)
- **Common Tasks**: [DEVELOPMENT.md](DEVELOPMENT.md#common-development-tasks)
- **Testing**: [DEVELOPMENT.md](DEVELOPMENT.md#testing)
- **Debugging**: [DEVELOPMENT.md](DEVELOPMENT.md#debugging)
- **Contributing**: [DEVELOPMENT.md](DEVELOPMENT.md#contributing-guidelines)

### Troubleshooting

- **Connection Issues**: [TROUBLESHOOTING.md](TROUBLESHOOTING.md#connection-issues)
- **Docker Issues**: [TROUBLESHOOTING.md](TROUBLESHOOTING.md#docker-issues)
- **Application Issues**: [TROUBLESHOOTING.md](TROUBLESHOOTING.md#application-issues)
- **Database Issues**: [TROUBLESHOOTING.md](TROUBLESHOOTING.md#database-issues)
- **Performance Issues**: [TROUBLESHOOTING.md](TROUBLESHOOTING.md#performance-issues)
- **Network Issues**: [TROUBLESHOOTING.md](TROUBLESHOOTING.md#network-issues)
- **Frontend Issues**: [TROUBLESHOOTING.md](TROUBLESHOOTING.md#frontend-issues)

---

## 🎯 By Feature

### Dark Ships Tracking

**What it is**: Real-time detection of ships that go offline (AIS signal loss)

**Documentation**:
1. [README.md#dark-ships-feature](README.md#dark-ships-feature) — Feature overview
2. [ARCHITECTURE.md#scenario-2-ship-goes-dark](ARCHITECTURE.md#scenario-2-ship-goes-dark) — How it works
3. [API_DOCUMENTATION.md#dark-ships-api-endpoints](API_DOCUMENTATION.md#dark-ships-api-endpoints-new) — API endpoints
4. [DATABASE.md#table-1-dark_ship_events](DATABASE.md#table-1-dark_ship_events) — Database schema
5. [TROUBLESHOOTING.md#dark-ship-detection-not-working](TROUBLESHOOTING.md#dark-ship-detection-not-working) — Issues

### Real-time Ship Tracking

**What it is**: Live AIS data streaming and vessel positioning

**Documentation**:
1. [ARCHITECTURE.md#scenario-1-real-time-ship-detection](ARCHITECTURE.md#scenario-1-real-time-ship-detection) — How it works
2. [API_DOCUMENTATION.md#6-get-live-ships](API_DOCUMENTATION.md#6-get-live-ships) — API endpoint
3. [TROUBLESHOOTING.md#no-ships-appearing-on-map](TROUBLESHOOTING.md#no-ships-appearing-on-map) — Issues

### Satellite Imagery

**What it is**: Multispectral satellite analysis for site detection

**Documentation**:
1. [ARCHITECTURE.md#2-copernicus-data-space-ecosystem](ARCHITECTURE.md#2-copernicus-data-space-ecosystem) — Integration details
2. [README.md#getting-started](README.md#getting-started) — Setup credentials
3. [TROUBLESHOOTING.md#copernicus-authentication-failed](TROUBLESHOOTING.md#copernicus-authentication-failed) — Issues

### Aircraft Tracking

**What it is**: Real-time aircraft positioning from OpenSky Network

**Documentation**:
1. [ARCHITECTURE.md#4-opensky-network-api](ARCHITECTURE.md#4-opensky-network-api) — Integration details
2. [API_DOCUMENTATION.md#7-get-live-aircraft](API_DOCUMENTATION.md#7-get-live-aircraft) — API endpoint
3. [TROUBLESHOOTING.md#opensky-network-unavailable](TROUBLESHOOTING.md#opensky-network-unavailable) — Issues

---

## 📁 File-by-File Reference

### README.md
Main user documentation
- **Audience**: End users, getting started
- **Key Sections**: Features, prerequisites, setup, deployment, usage
- **Length**: ~450 lines
- **Status**: Complete with documentation index

### ARCHITECTURE.md
System design and technical architecture
- **Audience**: Developers, architects, technical staff
- **Key Sections**: Overview, components, data flows, integrations, performance, security
- **Length**: ~700 lines
- **Status**: Complete with diagrams and examples

### API_DOCUMENTATION.md
Complete REST API reference
- **Audience**: API consumers, developers, integrators
- **Key Sections**: Dark ships endpoints, real-time data, error handling, examples
- **Length**: ~800 lines
- **Status**: Complete with curl examples and JSON responses

### DATABASE.md
Database schema and operations
- **Audience**: Database admins, developers
- **Key Sections**: Schema, tables, queries, maintenance, performance, troubleshooting
- **Length**: ~700 lines
- **Status**: Complete with SQL examples

### DEVELOPMENT.md
Development setup and contribution guide
- **Audience**: Developers, contributors
- **Key Sections**: Setup, code style, common tasks, testing, debugging, git workflow
- **Length**: ~900 lines
- **Status**: Complete with code examples

### TROUBLESHOOTING.md
Common issues and solutions
- **Audience**: All technical roles
- **Key Sections**: Connection issues, Docker issues, database issues, performance, support
- **Length**: ~800 lines
- **Status**: Complete with diagnostic steps

### DOCKER_DEPLOY.md
Extended Docker deployment guide
- **Audience**: DevOps, system administrators
- **Key Sections**: Prerequisites, image building, container running, monitoring
- **Length**: ~300 lines
- **Status**: Complete from earlier setup

---

## 🔗 Cross-References

### Architecture → API
- System design references API endpoints
- See [API_DOCUMENTATION.md](API_DOCUMENTATION.md) for exact specifications

### API → Database
- API operations interact with database tables
- See [DATABASE.md](DATABASE.md) for schema details

### Database → Architecture
- Database design supports system architecture
- See [ARCHITECTURE.md](ARCHITECTURE.md) for design rationale

### Development → All
- Development guide references architecture and API
- See [DEVELOPMENT.md](DEVELOPMENT.md) for contribution workflow

### Troubleshooting → All
- Troubleshooting references all documents
- Cross-links to specific solutions throughout documentation

---

## 📊 Documentation Statistics

| Document | Lines | Last Updated | Completeness |
|----------|-------|--------------|--------------|
| README.md | ~500 | June 21, 2026 | 100% |
| ARCHITECTURE.md | ~700 | June 21, 2026 | 100% |
| API_DOCUMENTATION.md | ~800 | June 21, 2026 | 100% |
| DATABASE.md | ~700 | June 21, 2026 | 100% |
| DEVELOPMENT.md | ~900 | June 21, 2026 | 100% |
| TROUBLESHOOTING.md | ~800 | June 21, 2026 | 100% |
| DOCKER_DEPLOY.md | ~300 | June 5, 2026 | 95% |
| **Total** | **~5,300** | — | **99%** |

---

## 🚀 Getting Help

### By Question Type

**"How do I install Epic Archer?"**
→ [README.md#getting-started](README.md#getting-started)

**"How do I get API keys?"**
→ [README.md#step-1-get-your-api-keys](README.md#step-1-get-your-api-keys)

**"What's the REST API?"**
→ [API_DOCUMENTATION.md](API_DOCUMENTATION.md)

**"How does dark ship detection work?"**
→ [ARCHITECTURE.md#scenario-2-ship-goes-dark](ARCHITECTURE.md#scenario-2-ship-goes-dark)

**"What's the database schema?"**
→ [DATABASE.md#database-schema](DATABASE.md#database-schema)

**"I want to contribute code"**
→ [DEVELOPMENT.md](DEVELOPMENT.md)

**"Something isn't working"**
→ [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

**"How do I deploy to Docker?"**
→ [DOCKER_DEPLOY.md](DOCKER_DEPLOY.md) or [README.md#option-a-docker-deployment](README.md#option-a-docker-deployment)

**"What's the overall design?"**
→ [ARCHITECTURE.md](ARCHITECTURE.md)

---

## 📋 Checklist: Complete Documentation

- ✅ User guide with quick start (README.md)
- ✅ System architecture and design (ARCHITECTURE.md)
- ✅ Complete API reference (API_DOCUMENTATION.md)
- ✅ Database schema and operations (DATABASE.md)
- ✅ Development setup and contribution (DEVELOPMENT.md)
- ✅ Troubleshooting guide (TROUBLESHOOTING.md)
- ✅ Docker deployment guide (DOCKER_DEPLOY.md)
- ✅ Documentation index (this file)

---

## 📞 Support & Resources

### Documentation
- All documentation files included in repository
- GitHub: https://github.com/blue44elephant/Epic-Archer-Counter-Narcotics-tool-

### External Resources
- FastAPI Docs: https://fastapi.tiangolo.com/
- SQLite Docs: https://www.sqlite.org/
- Leaflet.js Docs: https://leafletjs.com/
- AISStream: https://www.aisstream.io/
- Copernicus: https://dataspace.copernicus.eu/

### Getting Help
1. **Check Documentation**: Search relevant doc files above
2. **Check Troubleshooting**: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
3. **GitHub Issues**: Report bugs or ask questions
4. **Logs**: Check application logs for error details

---

**Documentation Index Version**: 1.0.0  
**Status**: Complete and Comprehensive  
**Last Updated**: June 21, 2026
