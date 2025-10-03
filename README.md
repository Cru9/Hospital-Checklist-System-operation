# 📋 Sistema de Checklist Hospitalario

## 🌟 Descripción General

El **Sistema de Checklist Hospitalario** es una aplicación web desarrollada en Flask diseñada para el monitoreo diario de operaciones y condiciones en múltiples hospitales. Facilita la recolección de datos, generación de reportes y análisis estadísticos para una toma de decisiones informada.

---

## 🎯 Objetivos del Sistema

- ✅ **Automatización** del proceso de reportes diarios hospitalarios
- 📊 **Monitoreo en tiempo real** del cumplimiento de metas operativas
- 📈 **Análisis histórico** de tendencias y problemas recurrentes
- 🏢 **Gestión centralizada** de múltiples unidades hospitalarias
- 💾 **Backup automático** de la base de datos para prevenir pérdida de datos

---

## 🏥 Hospitales Soportados

| ID Hospital | Nombre Completo |
|-------------|-----------------|
| `hgz24`     | HGZ24           |
| `hgz27`     | HGZ27           |
| `hgz29`     | HGZ29           |
| `hgz48`     | HGZ48           |
| `gineco3a`  | Gineco 3A       |

---

## 🚀 Características Principales

### 🔐 Sistema de Autenticación
- Roles diferenciados (**Administrador** y **Hospital**)
- Contraseñas seguras con hash
- Registro de logs de acceso

### 📝 Checklist Diario
**5 categorías principales con items específicos:**
- 🏗️ **Conservación**: máquina de anestesia, aire acondicionado, agua, limpieza
- 👥 **Personal**: vacaciones, ausentismo
- 💰 **Finanzas**: pagos a proveedores, facturas pendientes
- 📦 **Abasto**: kits, medicamentos
- 💻 **Tics**: red, sistema, impresora, equipo dañado
- Campo "**Otro**" para cada categoría
- **Porcentaje de completitud automático**

### 🎯 Metas Operativas
- **Meta diaria**: 7 operaciones
- **Meta semanal**: 56 operaciones  
- **Meta quincenal**: 112 operaciones

### 🎛️ Panel de Control Administrativo
- Vista consolidada de todos los hospitales
- Estado de reportes diarios
- Progreso hacia metas
- Alertas de reportes faltantes

---

## 📊 Módulos de Análisis

| Módulo | Descripción |
|--------|-------------|
| **📈 Estadísticas** | Análisis por períodos personalizables |
| **📋 Tendencias Hospitalarias** | Seguimiento individual por hospital |
| **⚠️ Problemas Recurrentes** | Identificación de patrones |

---

## 🔒 Sistema de Seguridad

- **📋 Logs de actividad**: Registro completo de acciones
- **💾 Backup automático**: Respaldo diario de la base de datos
- **🔄 Backup manual**: Función de respaldo bajo demanda

---

## 🛠️ Instalación y Configuración

### Prerrequisitos
- **Python 3.8** o superior
- **pip** (gestor de paquetes de Python)

---

## 👥 Usuarios Predefinidos

### 👨‍💼 Administradores
| Usuario | Controleña | Rol |
|---------|------------|-----|
| `admin` | `admin123` | `admin` |

### 🏥 Hospitales
| Usuario | Contraseña | Hospital ID |
|---------|------------|-------------|
| `hgz24` | `pass24` | `hgz24` |
| `hgz27` | `pass27` | `hgz27` |
| `hgz29` | `pass29` | `hgz29` |
| `hgz48` | `pass48` | `hgz48` |
| `gineco3a` | `pass3a` | `gineco3a` |

---

## 🗃️ Estructura de la Base de Datos

### Tabla: `users`
- `id`: Identificador único
- `username`: Nombre de usuario único  
- `password`: Contraseña con hash
- `role`: Rol (`admin`/`hospital`)
- `hospital_id`: ID del hospital (solo para rol hospital)

### Tabla: `reports`
- `id`: Identificador único
- `hospital_id`: ID del hospital
- `date`: Fecha del reporte
- `checklist_data`: Datos del checklist en JSON
- `observations`: Observaciones adicionales
- `met_goal`: Indicador de meta cumplida
- `operations_performed`: Operaciones realizadas
- `submitted_by`: ID del usuario que envió
- `submitted_at`: Timestamp de envío

### Tabla: `logs` (NUEVA)
- `id`: Identificador único
- `user_id`: ID del usuario (puede ser NULL)
- `action`: Acción realizada
- `timestamp`: Fecha y hora de la acción
- `ip_address`: Dirección IP del usuario

---

## 🔄 Flujos de Trabajo

### Para Usuarios Hospital:
1. **Iniciar sesión** con credenciales del hospital
2. **Completar checklist diario**:
   - Marcar items completados
   - Agregar observaciones si es necesario
   - Indicar si se cumplió la meta operativa
   - Especificar número de operaciones si no se cumplió la meta
3. **Guardar reporte** - El sistema calcula automáticamente el porcentaje de completitud

### Para Administradores:
1. **Iniciar sesión** con credenciales de admin
2. **Panel de control** - Vista general del estado de todos los hospitales
3. **Estadísticas** - Análisis detallado por períodos
4. **Tendencias** - Seguimiento individual por hospital
5. **Logs** - Revisión de actividad del sistema
6. **Backup** - Gestión de respaldos de base de datos

---

## 📈 Métricas y Análisis

### Métricas Principales
- **📊 Porcentaje de Completitud del Checklist**
- **✅ Cumplimiento de Metas Operativas**
- **📈 Tendencias Temporales**

### Gráficos y Visualizaciones
- **📅 Operaciones por día**: Línea temporal
- **📋 Completitud de unidad**: Línea temporal  
- **🎯 Metas históricas**: Gráfico de barras por hospital
- **📝 Análisis de items del checklist**: Porcentajes de completitud

---

## 📱 Funcionalidades por Módulo

| Módulo | Funcionalidades |
|--------|----------------|
| **📝 Checklist Diario** | Formulario dinámico, campos "Otro", cálculo automático |
| **🎛️ Dashboard Administrativo** | Vista consolidada, alertas, métricas |
| **📊 Estadísticas** | Filtros personalizables, gráficos, exportación |
| **📈 Tendencias Hospitalarias** | Selección específica, identificación de problemas |
| **📋 Logs y Auditoría** | Visualización de actividad, filtrado, información de IP |
| **💾 Backup** | Respaldo automático/manual, notificaciones |

---

## 🔧 Mantenimiento y Operación

### ⏰ Tareas Programadas
- **Backup automático**: Diario a las 2:00 AM
- **Limpieza de logs**: Manual (próxima característica)
- **Mantenimiento de BD**: Automático mediante SQLite

### 👁️ Monitoreo Recomendado
- 📁 Espacio en disco para backups
- ⚠️ Logs de errores en la aplicación
- 💾 Uso de memoria del servidor
- 👥 Actividad de usuarios

---

## ℹ️ Información del Proyecto

- **Versión**: 1.0
- **Última Actualización**: 03/10/2025  
- **Desarrollado por**: Equipo de Desarrollo Hospitalario

---

<div align="center">

### 🚀 **Sistema diseñado para la excelencia en cuidado hospitalario**

</div>